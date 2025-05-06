# Article 2: Setting up PostgreSQL and Hive Metastore

*Date: 2025-05-06*
*Previous Article: [Article 1: Initial Kubernetes Cluster Survey and Big Data Stack Selection](./01-initial-survey-and-stack-selection.md)*

## Introduction

In the previous article, we surveyed our Kubernetes cluster (`k8s.example.internal`) and decided on a target architecture for our Big Data stack: Minio (Data Lake), PostgreSQL (Metastore DB), Hive Metastore, Spark, and Trino.

This article focuses on the foundational step: deploying a dedicated **PostgreSQL** database and the **Apache Hive Metastore** service within our designated `bigdata` namespace. The Hive Metastore will use this PostgreSQL instance to store metadata about tables residing in our Minio data lake.

## Step 1: Preparing the Namespace and Secrets

We need a dedicated namespace and secrets to store credentials securely.

1.  **Create Namespace (if not already done):**
    All components of our Big Data stack will reside in the `bigdata` namespace for isolation.
    ```bash
    kubectl create namespace bigdata
    ```

2.  **Create PostgreSQL Secret:**
    This secret will hold the username, password, and database name for the new PostgreSQL instance that Hive Metastore will use. **Remember to use strong, unique passwords in a real environment!**
    ```bash
    # Define credentials (replace password!)
    DB_USER="hiveuser"
    DB_PASSWORD="AnotherSecurePassword456" # USE A STRONG PASSWORD!
    DB_NAME="hive_metastore"

    # Create the secret
    kubectl create secret generic postgres-bigdata-secret \
      --from-literal=POSTGRES_USER="$DB_USER" \
      --from-literal=POSTGRES_PASSWORD="$DB_PASSWORD" \
      --from-literal=POSTGRES_DB="$DB_NAME" \
      -n bigdata
    ```
    *(This secret resides in the `bigdata` namespace).*

3.  **Create Minio Secret:**
    This secret will hold the access and secret keys for connecting to our existing Minio instance. These keys will be used later by Hive Metastore (potentially, though less common), Trino, and Spark.
    ```bash
    # Replace with your actual Minio keys
    MINIO_ACCESS_KEY_VALUE="YOUR_MINIO_ACCESS_KEY"
    MINIO_SECRET_KEY_VALUE="YOUR_MINIO_SECRET_KEY"

    # Create the secret
    kubectl create secret generic minio-s3-secret \
      --from-literal=MINIO_ACCESS_KEY="$MINIO_ACCESS_KEY_VALUE" \
      --from-literal=MINIO_SECRET_KEY="$MINIO_SECRET_KEY_VALUE" \
      -n bigdata
    ```

## Step 2: Deploying PostgreSQL using StatefulSet

We will deploy a standalone PostgreSQL instance using a StatefulSet for stable network identity and persistent storage provided by Longhorn.

1.  **Create the Manifest (`postgres-bigdata.yaml`):**
    This manifest defines the Secret (already created above, but included for completeness), PVC, Headless Service, StatefulSet, and ClusterIP Service.
    *(The full content of `postgres-bigdata.yaml` can be found here: [../components/01-postgresql/postgres-bigdata.yaml](../components/01-postgresql/postgres-bigdata.yaml)*

    *Key configurations within the manifest:*
    *   Uses the `postgres:15` image.
    *   References the `postgres-bigdata-secret` for credentials.
    *   Uses `volumeClaimTemplates` with `storageClassName: longhorn` to create a Persistent Volume for data.
    *   Includes basic `readinessProbe` and `livenessProbe`.
    *   Sets `securityContext` to run as the `postgres` user (UID/GID 999) and comply with the `baseline` Pod Security Standard (assuming the namespace label was applied as discussed during troubleshooting).

2.  **Apply the Manifest:**
    ```bash
    # Ensure the pod security policy for the namespace is appropriate
    # For baseline (applied previously):
    # kubectl label --overwrite ns bigdata pod-security.kubernetes.io/enforce=baseline

    # Apply the PostgreSQL manifest
    kubectl apply -f ../components/01-postgresql/postgres-bigdata.yaml
    ```
    *(Note: `kubectl apply` might still show warnings about PodSecurity `restricted:latest` due to client-side validation, but the pod should start successfully if the `baseline` label is on the namespace).*

3.  **Verify Deployment:**
    Wait for the pod to become ready.
    ```bash
    kubectl get pods -n bigdata -l app=postgres-bigdata -w
    # Wait for postgres-0 to be Running and READY 1/1

    kubectl get pvc -n bigdata -l app=postgres-bigdata
    # Check PVC status is Bound

    kubectl get svc -n bigdata -l app=postgres-bigdata
    # Verify postgres-headless (ClusterIP=None) and postgres-svc (ClusterIP assigned) exist
    ```

## Step 3: Deploying Hive Metastore using Helm

Since the Bitnami Helm chart for Hive is no longer available or easily accessible, we identified the `ilum/ilum-hive-metastore` chart as the most promising alternative during our investigation.

1.  **Add the Ilum Helm Repository:**
    ```bash
    helm repo add ilum https://charts.ilum.cloud
    helm repo update
    ```

2.  **Create Metastore Database Secret:**
    Hive Metastore needs its own secret containing the connection details for the PostgreSQL database we just created.
    ```bash
    # Get the password from the PostgreSQL secret
    PG_PASSWORD=$(kubectl get secret postgres-bigdata-secret -n bigdata -o jsonpath='{.data.POSTGRES_PASSWORD}' | base64 --decode)

    # Create the secret for Hive Metastore
    kubectl create secret generic hive-metastore-postgresql-secret \
      --from-literal=HIVE_METASTORE_DB_HOST='postgres-svc.bigdata.svc.cluster.local' \
      --from-literal=HIVE_METASTORE_DB_PORT='5432' \
      --from-literal=HIVE_METASTORE_DB_NAME='hive_metastore' \
      --from-literal=HIVE_METASTORE_DB_USER='hiveuser' \
      --from-literal=HIVE_METASTORE_DB_PASSWORD="$PG_PASSWORD" \
      -n bigdata
    ```

3.  **Prepare `ilum-metastore-values.yaml`:**
    We need to configure the Ilum chart to use our external PostgreSQL and specify Minio as the default warehouse location.
    *(The final content of `ilum-metastore-values.yaml` can be found here: [../components/02-hive-metastore/ilum-metastore-values.yaml](../components/02-hive-metastore/ilum-metastore-values.yaml)*

    *Key configurations within the values file:*
    *   `postgresql.host`: `postgres-svc.bigdata.svc.cluster.local`
    *   `postgresql.database`: `hive_metastore`
    *   `postgresql.auth.username`: `hiveuser`
    *   **(Limitation)** This chart requires passing sensitive info (Postgres password, Minio keys) via `--set` as it doesn't directly support `existingSecret` for these specific fields in the tested version.
    *   `storage.type`: `s3`
    *   `storage.metastore.warehouse`: `s3a://<your-minio-bucket>/warehouse/` (e.g., `s3a://spark-data/warehouse/`) - **Replace `<your-minio-bucket>`!**
    *   `storage.s3.host`: `minio.minio.svc.cluster.local` (Internal Minio service)
    *   `storage.s3.port`: `9000`

4.  **Install Hive Metastore:**
    Retrieve secrets and install using Helm, passing sensitive values via `--set`.
    ```bash
    # Get passwords/keys from secrets
    PG_PASSWORD=$(kubectl get secret hive-metastore-postgresql-secret -n bigdata -o jsonpath='{.data.HIVE_METASTORE_DB_PASSWORD}' | base64 --decode)
    MINIO_ACCESS_KEY=$(kubectl get secret minio-s3-secret -n bigdata -o jsonpath='{.data.MINIO_ACCESS_KEY}' | base64 --decode)
    MINIO_SECRET_KEY=$(kubectl get secret minio-s3-secret -n bigdata -o jsonpath='{.data.MINIO_SECRET_KEY}' | base64 --decode)

    # Install the chart
    helm install ilum-hive-metastore ilum/ilum-hive-metastore \
      --namespace bigdata \
      -f ../components/02-hive-metastore/ilum-metastore-values.yaml \
      --set postgresql.auth.password="$PG_PASSWORD" \
      --set storage.s3.accessKey="$MINIO_ACCESS_KEY" \
      --set storage.s3.secretKey="$MINIO_SECRET_KEY"
    ```
    *(Again, ignore client-side PodSecurity warnings if the namespace policy is `baseline`)*.

5.  **Verify Deployment:**
    ```bash
    kubectl get pods -n bigdata -l app.kubernetes.io/instance=ilum-hive-metastore -w
    # Wait for the main metastore pod (e.g., ilum-hive-metastore-0) to be Running and READY 1/1
    # Also check for the init-schema job to complete: kubectl get jobs -n bigdata

    kubectl get svc -n bigdata -l app.kubernetes.io/instance=ilum-hive-metastore
    # Verify the ilum-hive-metastore service exists (usually on port 9083)

    # Check logs for successful connection to Postgres
    METASTORE_POD=$(kubectl get pods -n bigdata -l app.kubernetes.io/instance=ilum-hive-metastore,app.kubernetes.io/component=metastore -o jsonpath='{.items[0].metadata.name}')
    kubectl logs $METASTORE_POD -n bigdata
    ```

## Conclusion

At this point, we have successfully deployed a dedicated PostgreSQL database and the Apache Hive Metastore service within the `bigdata` namespace. The Metastore is configured to use our PostgreSQL instance for storing metadata and understands where our data lake (Minio) is located.

This forms the crucial foundation for our data platform. In the next article, we will deploy Trino and configure it to use this Hive Metastore, enabling SQL queries against our future data lake.

---
*Next Article: [Article 3: Deploying and Configuring Trino](./03-trino-setup-and-integration.md) (Link to be created)*

