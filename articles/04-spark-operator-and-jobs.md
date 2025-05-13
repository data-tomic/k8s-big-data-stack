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

## Step 5: Troubleshooting TLS for Harbor (If Encountered during Spark Application Image Pull)

During our deployment, a common issue when pulling images from a private Harbor registry secured with a custom SSL certificate (e.g., self-signed or signed by an internal CA) is `ImagePullBackOff` with an error message similar to:

`Failed to pull image "harbor.k8s.example.internal/bigdata/spark-app:latest": rpc error: code = Unknown desc = failed to pull and unpack image "harbor.k8s.example.internal/bigdata/spark-app:latest": failed to resolve reference "harbor.k8s.example.internal/bigdata/spark-app:latest": failed to do request: Head "https://harbor.k8s.example.internal/v2/bigdata/spark-app/manifests/latest": tls: failed to verify certificate: x509: certificate signed by unknown authority`

This error indicates that the Kubernetes worker nodes (where `kubelet` and the container runtime operate) do not trust the Certificate Authority (CA) that signed Harbor's SSL certificate. For Talos OS, which uses a declarative configuration model, this requires updating the machine configuration on each relevant node.

**Solution for Talos OS:**

The core idea is to provide the CA certificate (or the full chain if intermediate CAs are involved) to each Talos node and configure the container runtime (containerd, in Talos's case) to trust this CA for your specific Harbor registry.

1.  **Obtain Harbor's CA Certificate Chain:**
    You need the PEM-encoded CA certificate(s) that signed your Harbor's SSL certificate.
    *   **If using an internal Corporate CA:** Obtain the root CA certificate and any intermediate CA certificates from your PKI team.
    *   **If Harbor uses a self-signed certificate:** The certificate Harbor uses *is* its own CA.
    *   **To retrieve certificates from a live server (use with caution, verify authenticity):**
        ```bash
        # Replace harbor.k8s.example.internal with your Harbor FQDN
        openssl s_client -showcerts -connect harbor.k8s.example.internal:443 < /dev/null 2>/dev/null | \
        awk '/BEGIN CERTIFICATE/,/END CERTIFICATE/{ if(/BEGIN CERTIFICATE/){a++}; out="harbor.ca."a".crt"; print >out}'
        ```
        This command will attempt to extract all certificates in the chain presented by the server. You'll typically need the root CA (often the last one in the chain if multiple are presented, or the only one if self-signed). Let's assume you save the necessary CA certificate(s) into a file named `harbor-ca-chain.pem`. Ensure it's in PEM format (`-----BEGIN CERTIFICATE-----...-----END CERTIFICATE-----`). If you have multiple (root + intermediate), concatenate them into this single file in order (server cert's issuer, then that issuer's issuer, up to the root).

2.  **Prepare the Talos Machine Configuration Patch:**
    You will need to modify the machine configuration files for your Talos worker nodes (and control-plane nodes if they also need to pull images from this Harbor, though typically image pulls for workloads happen on workers).

    For each node, you'll add/update the `machine.files` section to place the CA certificate on the node, and the `machine.registries` section to configure containerd.

    Create a patch file (e.g., `talos-harbor-ca-patch.yaml`) or directly edit your node's configuration YAML.

    ```yaml
    # Example patch content or section to add/modify in a node's Talos configuration YAML
    # (e.g., talos-wk-01.yaml)
    machine:
      # ... other machine configurations ...

      files:
        - path: /etc/ssl/certs/harbor.k8s.example.internal.pem # Path on the Talos node where the CA cert will be stored
          permissions: 0644
          content: |
            -----BEGIN CERTIFICATE-----
            MII... (Full content of your harbor-ca-chain.pem) ...
            -----END CERTIFICATE-----
            # If you have multiple concatenated certs, they all go here.

      registries:
        # Mirrors and insecure registries configuration (deprecated in favor of config below for CAs)
        # mirrors:
        #   "harbor.k8s.example.internal":
        #     overridePath: true # if harbor is on non-standard port
        #     endpoint:
        #       - "https://harbor.k8s.example.internal"
        # containerd specific configuration for trusted CAs
        config:
          # The key here MUST be your Harbor's FQDN
          "harbor.k8s.example.internal":
            # This tells containerd to trust the CA cert(s) in this file for this specific registry
            caFile: "/etc/ssl/certs/harbor.k8s.example.internal.pem"

            # Alternative for completely insecure access (NOT RECOMMENDED FOR PRODUCTION):
            # tls:
            #   insecureSkipVerify: true
    ```
    *   **`machine.files.path`:** Choose a suitable path on the node, e.g., `/etc/ssl/certs/harbor.k8s.example.internal.pem`.
    *   **`machine.files.content`:** Paste the full PEM content of your `harbor-ca-chain.pem` here, ensuring correct YAML indentation.
    *   **`machine.registries.config`:** This is the modern way to configure registry mirrors and TLS settings for containerd in Talos. The key under `config` must be the FQDN of your Harbor registry.
    *   **`caFile`:** Points to the path where you placed the CA certificate in `machine.files`.

3.  **Apply Updated Configuration to Talos Nodes:**
    For each worker node (and any control plane nodes if necessary), apply the updated configuration.
    **Warning:** Applying a new machine configuration typically triggers a node reboot in Talos to ensure all changes are correctly applied. Plan for this downtime or perform rolling updates.

    ```bash
    # For each node, using its IP address and the updated YAML configuration file for that node
    talosctl apply-config --insecure -n <node1-ip-address> -f <path-to-updated-node1-config.yaml>
    talosctl apply-config --insecure -n <node2-ip-address> -f <path-to-updated-node2-config.yaml>
    # ... and so on for all relevant nodes.
    ```
    Wait for each node to reboot and rejoin the cluster. You can monitor this with `talosctl health -n <node-ip>` or `kubectl get nodes -w`.

4.  **Verify Image Pull:**
    After all relevant nodes have been updated and are `Ready`, try deploying your `SparkApplication` again or simply try to pull an image from Harbor on one of the nodes (e.g., by creating a test pod that uses an image from Harbor).
    ```bash
    # Example test pod
    # kubectl run harbor-test --image=harbor.k8s.example.internal/bigdata/spark-app:latest -n bigdata --rm -it -- /bin/true
    ```
    The `ImagePullBackOff` error related to TLS should now be resolved.

This detailed procedure ensures that the container runtime on your Talos OS nodes trusts your Harbor's SSL certificate, allowing `kubectl` (via kubelet) to pull images securely.

## Conclusion

The Spark Operator is now installed, and we have successfully run a test Spark application, pulling a custom image from our private Harbor registry. Key troubleshooting steps for image pulling (credentials, TLS trust for custom CAs on Talos OS) and application execution (OOM) have been addressed. The foundation is laid for running more complex Spark ETL/ELT jobs that can interact with MinIO and Hive Metastore.

---
*Next Article: [Article 5: Deploying Apache Superset for Business Intelligence](./05-superset-deployment.md)*
