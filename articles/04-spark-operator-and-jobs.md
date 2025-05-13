# Article 4: Setting up Spark Operator and Running Spark Jobs

*Date: 2025-05-13*
*Previous Article: [Article 3: Deploying and Configuring Trino](./03-trino-setup-and-integration.md)*

## Introduction

With our data lake foundation (Minio), metadata layer (PostgreSQL + Hive Metastore), and interactive query engine (Trino) in place, the next critical component is a robust batch processing and data transformation engine. For this, we will use Apache Spark, managed декларативно within Kubernetes using the Spark Operator.

This article details the installation of the Spark Operator, configuration of a dedicated ServiceAccount for Spark applications, building a custom Spark image, and running a test Spark application that interacts with our Harbor registry and MinIO.

## Step 1: Installing the Spark Operator

The Spark Operator simplifies the management and submission of Spark applications on Kubernetes. We will install it using its Helm chart.

1.  **Add the Spark Operator Helm Repository:**
    ```bash
    helm repo add spark-operator https://googlecloudplatform.github.io/spark-on-k8s-operator
    helm repo update
    ```

2.  **Create Namespace for Spark Operator (if desired):**
    While Spark applications will run in the `bigdata` namespace, the operator itself can reside in its own namespace for better organization. We will use `spark-operator`.
    ```bash
    kubectl create namespace spark-operator
    ```

3.  **Install the Spark Operator:**
    We'll install the operator into the `spark-operator` namespace and enable it to watch for `SparkApplication` resources in the `bigdata` namespace.
    *Refer to `../components/04-spark/spark-operator-values.yaml` for any specific values used during installation.*
    ```bash
    helm install spark-operator spark-operator/spark-operator \
      --namespace spark-operator \
      --set sparkJobNamespace=bigdata \
      --set webhook.enable=true \
      # -f ../components/04-spark/spark-operator-values.yaml # Uncomment if you have custom values
    ```

4.  **Verify Operator Deployment:**
    ```bash
    kubectl get pods -n spark-operator -w
    # Wait for pods like spark-operator-controller-... and spark-operator-webhook-... to be Running
    ```

## Step 2: Configuring ServiceAccount and RBAC for Spark Applications

Spark applications running in the `bigdata` namespace will need a dedicated ServiceAccount with permissions to create and manage executor pods, and also to pull images from our private Harbor registry.

1.  **Create `spark-sa` ServiceAccount and RBAC in `bigdata` namespace:**
    The manifest `../components/00-namespace-rbac/spark-rbac.yaml` should define the `ServiceAccount`, `Role`, and `RoleBinding`.
    *(File: `../components/00-namespace-rbac/spark-rbac.yaml`)*
    ```yaml
    # Example content for spark-rbac.yaml
    apiVersion: v1
    kind: ServiceAccount
    metadata:
      name: spark-sa
      namespace: bigdata
    ---
    apiVersion: rbac.authorization.k8s.io/v1
    kind: Role
    metadata:
      namespace: bigdata
      name: spark-role
    rules:
    - apiGroups: [""]
      resources: ["pods", "services", "configmaps", "secrets"]
      verbs: ["get", "list", "watch", "create", "delete", "update", "patch"]
    - apiGroups: [""]
      resources: ["pods/log"]
      verbs: ["get", "list", "watch"]
    # Add more permissions if needed, e.g., for PVCs
    ---
    apiVersion: rbac.authorization.k8s.io/v1
    kind: RoleBinding
    metadata:
      name: spark-role-binding
      namespace: bigdata
    subjects:
    - kind: ServiceAccount
      name: spark-sa
      namespace: bigdata
    roleRef:
      kind: Role
      name: spark-role
      apiGroup: rbac.authorization.k8s.io
    ```
    Apply the manifest:
    ```bash
    kubectl apply -f ../components/00-namespace-rbac/spark-rbac.yaml
    ```
    *(Note: `spark-operator-extra-rbac.yaml` in your `components/04-spark` might be for the operator itself, or additional roles. Clarify its purpose if different from the SA's RBAC).*

2.  **Create Harbor Credentials Secret (`harbor-creds`):**
    ```bash
    HARBOR_SERVER="harbor.k8s.example.internal" # Placeholder
    HARBOR_USER="your-harbor-user"      # Placeholder
    HARBOR_PASSWORD="YOUR_HARBOR_PASSWORD_PLACEHOLDER"
    HARBOR_EMAIL="user@example.com"

    kubectl create secret docker-registry harbor-creds \
      --docker-server="$HARBOR_SERVER" \
      --docker-username="$HARBOR_USER" \
      --docker-password="$HARBOR_PASSWORD" \
      --docker-email="$HARBOR_EMAIL" \
      -n bigdata
    ```

3.  **Attach `imagePullSecrets` to `spark-sa` ServiceAccount:**
    ```bash
    kubectl patch serviceaccount spark-sa -n bigdata -p '{"imagePullSecrets": [{"name": "harbor-creds"}]}'
    ```

## Step 3: Preparing a Custom Spark Docker Image

1.  **`Dockerfile` for Spark:**
    *(Example location, adjust if needed: `../components/04-spark/spark-image/Dockerfile` - you might want a dedicated dir for image builds, e.g., `images/spark/Dockerfile`)*
    ```dockerfile
    FROM harbor.k8s.example.internal/bigdata/spark:3.5.5-debian-12-r5 # Your base Spark image
    # Add custom dependencies or scripts if necessary
    ```

2.  **Build and Push:**
    ```bash
    # cd to Dockerfile directory
    docker build -t harbor.k8s.example.internal/bigdata/spark-app:latest . # Use your Harbor & image name
    docker push harbor.k8s.example.internal/bigdata/spark-app:latest
    ```

## Step 4: Running a Test Spark Application

1.  **Python Script (`write_test.py`):**
    *(File: `../components/04-spark/spark-jobs/write_test.py`)*
    ```python
    # Content as previously defined
    from pyspark.sql import SparkSession
    # ...
    print("Spark Write Test application finished successfully.")
    spark.stop()
    ```

2.  **ConfigMap for the script:**
    *(Create a YAML, e.g., `../components/04-spark/spark-jobs/spark-script-cm.yaml`)*
    ```yaml
    apiVersion: v1
    kind: ConfigMap
    metadata:
      name: spark-write-script
      namespace: bigdata
    data:
      write_test.py: |
        # Paste content of write_test.py here
    ```
    Apply: `kubectl apply -f ../components/04-spark/spark-jobs/spark-script-cm.yaml`

3.  **`SparkApplication` Manifest:**
    *(File: `../components/04-spark/spark-test-write.yaml`)*
    ```yaml
    apiVersion: "sparkoperator.k8s.io/v1beta2"
    kind: SparkApplication
    metadata:
      name: spark-write-test
      namespace: bigdata
    spec:
      type: Python
      pythonVersion: "3"
      mode: cluster
      image: "harbor.k8s.example.internal/bigdata/spark-app:latest" # Your custom image
      imagePullPolicy: Always
      mainApplicationFile: "local:///app/write_test.py"
      sparkVersion: "3.5"
      restartPolicy:
        type: OnFailure
        onFailureRetries: 1
      driver:
        cores: 1
        memory: "1024m"
        serviceAccount: spark-sa
        envFrom:
          - secretRef: { name: minio-s3-secret } # For MinIO
        volumeMounts:
          - name: spark-script-volume
            mountPath: /app
      executor:
        cores: 1
        instances: 1
        memory: "1024m"
        envFrom:
          - secretRef: { name: minio-s3-secret } # For MinIO
      volumes:
        - name: spark-script-volume
          configMap: { name: spark-write-script }
      # sparkConf:
      #   "spark.hadoop.fs.s3a.endpoint": "http://minio.minio.svc.cluster.local:9000"
      #   # ... other S3A and Hive Metastore configs ...
    ```

4.  **Deploy and Monitor:**
    ```bash
    kubectl apply -f ../components/04-spark/spark-test-write.yaml
    kubectl get sparkapplication spark-write-test -n bigdata -w
    # ... other monitoring commands ...
    ```

## Step 5: Troubleshooting TLS for Harbor (If Encountered)

*(Content as previously defined, explaining Talos OS configuration for custom CA)*

## Conclusion

*(Content as previously defined)*

---
*Next Article: [Article 5: Deploying Apache Superset for Business Intelligence](./05-superset-deployment.md)*
