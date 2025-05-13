# Article 5: Deploying Apache Superset for Business Intelligence

*Date: 2025-05-13*
*Previous Article: [Article 4: Setting up Spark Operator and Running Spark Jobs](./04-spark-operator-and-jobs.md)*

## Introduction

With our data processing (Spark) and interactive query (Trino) layers established, the final piece for data exploration and visualization is a Business Intelligence (BI) tool. We've chosen Apache Superset for its rich feature set, open-source nature, and strong Kubernetes support via Helm.

This article details the deployment of Apache Superset, including building a custom Docker image to include necessary database drivers, configuring TLS with Traefik and Cert-Manager, and resolving critical configuration for the `SECRET_KEY`.

## Step 1: Prerequisites and Namespace

1.  **Namespace:** We will deploy Superset in its own dedicated namespace for isolation.
    ```bash
    kubectl create namespace superset
    ```
2.  **Ingress & Certificates:** Ensure Traefik (or your chosen Ingress controller) and Cert-Manager (with a `ClusterIssuer`, e.g., `pki-ca`) are operational.
3.  **Docker Registry:** Access to Harbor (e.g., `harbor.k8s.example.internal`) for the custom Superset image.
4.  **Helm:** Version 3+.

## Step 2: Preparing a Custom Superset Docker Image (with `psycopg2`)

The default Superset image used by the Helm chart (`superset/superset:0.14.2`, which pulls `apachesuperset.docker.scarf.sh/apache/superset:4.1.2`) was found to be missing the `psycopg2` Python driver, which is necessary for Superset's metadata database (PostgreSQL) and for connecting to PostgreSQL data sources.

1.  **`Dockerfile` for Superset:**
    *(File: `../components/05-superset/Dockerfile`)*
    ```dockerfile
    # Use the same base image as the chart for compatibility
    FROM apachesuperset.docker.scarf.sh/apache/superset:4.1.2 # Or your preferred base

    USER root
    # Install psycopg2-binary (simpler than compiling psycopg2)
    # Also upgrade pip and setuptools as a good practice
    RUN pip install --no-cache-dir --upgrade pip setuptools && \
        pip install --no-cache-dir psycopg2-binary
    # If Pillow is needed for screenshots/reports, add it here:
    # RUN pip install --no-cache-dir Pillow

    # Switch back to the default superset user if known/needed
    # USER superset
    ```

2.  **Build and Push Image to Harbor:**
    ```bash
    # Ensure you are in the directory containing the Dockerfile (e.g., ../components/05-superset/)
    docker build -t harbor.k8s.example.internal/bigdata/superset-with-psycopg2:4.1.2 .
    docker push harbor.k8s.example.internal/bigdata/superset-with-psycopg2:4.1.2
    ```

## Step 3: Configuring and Installing Superset via Helm

The deployment of Superset using the `superset/superset` chart (version `0.14.2`) presented challenges, primarily around setting the `SECRET_KEY`. The reliable method was found to be setting the `SUPERSET_SECRET_KEY` environment variable, which is achieved by defining it in the `extraSecretEnv` section of `values.yaml`. This populates the `superset-env` Kubernetes Secret, which is then consumed by the Superset pods.

1.  **Add Superset Helm Repository:**
    ```bash
    helm repo add superset https://apache.github.io/superset
    helm repo update
    ```

2.  **Prepare `superset-values.yaml`:**
    *(File: `../components/05-superset/superset-values.yaml`)*
    ```yaml
    # superset-values.yaml
    # Helm chart will use this secret name to source environment variables
    envFromSecret: "superset-env"

    # Defines keys that will be added to the 'superset-env' Kubernetes Secret
    extraSecretEnv:
      # This is the CORRECT way to set the secret key for this chart version,
      # as Superset will look for this environment variable.
      SUPERSET_SECRET_KEY: 'YOUR_VERY_STRONG_RANDOM_SECRET_KEY_HERE' # REPLACE THIS!

    image:
      repository: "harbor.k8s.example.internal/bigdata/superset-with-psycopg2" # Our custom image
      tag: "4.1.2" # Matches the base image version
      pullPolicy: IfNotPresent

    postgresql:
      enabled: true # Use the chart's bundled PostgreSQL for Superset's metadata
      persistence:
        enabled: true
        # size: 10Gi
      auth:
        username: "superset"
        # Password for the PostgreSQL user 'superset'.
        # This will be used by the chart to create the PG user and set its password.
        # Superset application will get this (and other DB connection details)
        # from the 'superset-env' secret, which is populated by the chart.
        password: "YOUR_POSTGRES_SUPERSET_USER_PASSWORD" # REPLACE THIS!
        database: "superset"

    redis:
      enabled: true # Use the chart's bundled Redis
      # auth:
      #   enabled: false # Default is no password for bundled Redis

    supersetNode: # Web server pods
      resources: { requests: { cpu: "500m", memory: "1Gi" }, limits: { cpu: "1", memory: "2Gi" } }
    supersetWorker: # Celery worker pods
      resources: { requests: { cpu: "500m", memory: "1Gi" }, limits: { cpu: "1", memory: "2Gi" } }
    supersetCeleryBeat: # For scheduled tasks, alerts & reports
      # enabled: true # Enable if you need alerts & reports
      resources: { requests: { cpu: "200m", memory: "512Mi" }, limits: { cpu: "500m", memory: "1Gi" } }

    ingress:
      enabled: true
      ingressClassName: "traefik" # Your Ingress controller class
      hosts:
        - "superset.k8s.example.internal" # Your desired hostname for Superset
      path: /
      pathType: Prefix
      tls:
        - secretName: "superset-tls" # cert-manager will store the cert here
          hosts:
            - "superset.k8s.example.internal"
      annotations:
        cert-manager.io/cluster-issuer: "pki-ca" # Your cert-manager ClusterIssuer

    init:
      adminUser:
        username: "admin"
        password: "YOUR_INITIAL_ADMIN_PASSWORD" # !!! REPLACE & CHANGE IMMEDIATELY AFTER FIRST LOGIN !!!
        firstname: "Admin"
        lastname: "User"
        email: "admin@example.com" # Your admin email
    # loadExamples: false # Optionally disable example data for a clean start
    ```
    *Replace placeholders like `YOUR_VERY_STRONG_RANDOM_SECRET_KEY_HERE`, `YOUR_POSTGRES_SUPERSET_USER_PASSWORD`, `YOUR_INITIAL_ADMIN_PASSWORD`, `superset.k8s.example.internal`, `admin@example.com` with appropriate secure values and your specific FQDNs.*

3.  **Install/Upgrade Superset:**
    Chart version `0.14.2` (App Version `4.1.2`) was used.
    ```bash
    # It's good practice to delete the superset-env secret before an upgrade
    # if you've made changes that affect it (like SUPERSET_SECRET_KEY),
    # to ensure Helm recreates it correctly.
    # kubectl delete secret superset-env -n superset || true

    helm upgrade --install superset superset/superset \
      --namespace superset \
      -f ../components/05-superset/superset-values.yaml \
      --version 0.14.2
    ```
    *Using `upgrade --install` handles both initial install and subsequent upgrades.*

4.  **Force Pod Restart (Crucial After Secret/Config Changes):**
    To ensure all Superset components pick up the latest `superset-env` Secret (especially `SUPERSET_SECRET_KEY`) and the new image:
    ```bash
    kubectl delete pod -n superset -l release=superset
    ```
    *(This will delete web, worker, beat, and init-job pods related to the 'superset' release. Kubernetes will recreate them.)*

5.  **Verify Deployment and Access:**
    ```bash
    kubectl get pods -n superset -w
    # Wait for superset-web, superset-worker, superset-postgresql, superset-redis to be Running
    # and for a superset-init-db job/pod to be Completed.

    kubectl get ingress superset -n superset
    # Check ADDRESS field.

    kubectl get certificate superset-tls -n superset
    # Check READY status is True.

    kubectl get secret superset-env -n superset -o yaml
    # Verify SUPERSET_SECRET_KEY and DB/Redis connection variables are present and correctly populated.
    ```
    Once everything is up, access `https://superset.k8s.example.internal/`.
    Log in with the initial admin credentials (`init.adminUser.username` / `init.adminUser.password`) and **change the password immediately via the Superset UI (Security -> List Users).**

## Troubleshooting Summary for Superset

*   **`Refusing to start due to insecure SECRET_KEY`:** This was the most persistent issue. Resolved by:
    1.  Identifying that Superset expects this key via the `SUPERSET_SECRET_KEY` environment variable (as per Superset documentation).
    2.  Configuring the Helm chart to populate this environment variable by adding `SUPERSET_SECRET_KEY: 'your-key'` under the `extraSecretEnv` section in `superset-values.yaml`. This ensures the key is correctly placed into the `superset-env` Kubernetes Secret, which is then sourced by the Superset pods.
*   **`ModuleNotFoundError: No module named 'psycopg2'`:** The default Docker image lacked the PostgreSQL Python driver. Resolved by building a custom Docker image based on the chart's default, adding a step to `pip install psycopg2-binary`, and using this custom image in `superset-values.yaml`.
*   **Ingress Configuration Issues:** Initial attempts to configure Ingress paths failed. The working solution for chart version `0.14.2` involved specifying `hosts` as a simple list and `path`/`pathType` at the top level of the `ingress` section in `values.yaml`.
*   **Pod Restarts:** After applying `helm upgrade` with changes to secrets or images, a manual `kubectl delete pod -l release=superset` was often necessary to ensure all components picked up the latest configurations.

## Conclusion

Apache Superset is now successfully deployed and operational within our Kubernetes cluster, providing a robust and scalable Business Intelligence layer for our Big Data stack. The deployment journey, while challenging due to configuration intricacies of the `SECRET_KEY` and missing Python dependencies in the default image, ultimately yielded a working instance accessible via Traefik Ingress and secured with TLS managed by Cert-Manager.

Key takeaways include the importance of meticulously checking Helm chart documentation and default values for critical configuration parameters, and the flexibility offered by custom Docker images to address missing dependencies. With Superset ready, we can now connect it to our Trino query engine to visualize data from our MinIO data lake.

The next major component to integrate into our stack is Apache Airflow, which will serve as the orchestrator for our data pipelines.

---
*Next Article: [Article 6: Setting up Apache Airflow for Workflow Orchestration](./06-airflow-setup.md) (To be created)*
