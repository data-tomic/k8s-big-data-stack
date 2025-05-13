# Article 5: Deploying Apache Superset for Business Intelligence

*Date: 2025-05-13*
*Previous Article: [Article 4: Setting up Spark Operator and Running Spark Jobs](./04-spark-operator-and-jobs.md)*

## Introduction

With our data processing (Spark) and interactive query (Trino) layers established, the final piece for data exploration and visualization is a Business Intelligence (BI) tool. We've chosen Apache Superset for its rich feature set, open-source nature, and strong Kubernetes support via Helm.

This article details the deployment of Apache Superset, including building a custom Docker image to include necessary database drivers, configuring TLS with Traefik and Cert-Manager, and resolving critical configuration for the `SECRET_KEY`.

## Step 1: Prerequisites and Namespace

1.  **Namespace:**
    ```bash
    kubectl create namespace superset
    ```
2.  **Ingress & Certificates:** Ensure Traefik and Cert-Manager (with a `ClusterIssuer`, e.g., `pki-ca`) are operational.
3.  **Docker Registry:** Access to Harbor (e.g., `harbor.k8s.example.internal`) for the custom Superset image.
4.  **Helm:** Version 3+.

## Step 2: Preparing a Custom Superset Docker Image (with `psycopg2`)

The default Superset image used by the Helm chart (`superset/superset:0.14.2`, which pulls `apache/superset:4.1.2`) lacked the `psycopg2` Python driver.

1.  **`Dockerfile` for Superset:**
    *(File: `../components/05-superset/Dockerfile`)*
    ```dockerfile
    FROM apachesuperset.docker.scarf.sh/apache/superset:4.1.2 # Or your preferred base

    USER root
    RUN pip install --no-cache-dir --upgrade pip setuptools && \
        pip install --no-cache-dir psycopg2-binary
    # USER superset # If needed
    ```

2.  **Build and Push Image:**
    ```bash
    # cd to ../components/05-superset/
    docker build -t harbor.k8s.example.internal/bigdata/superset-with-psycopg2:4.1.2 .
    docker push harbor.k8s.example.internal/bigdata/superset-with-psycopg2:4.1.2
    ```

## Step 3: Configuring and Installing Superset via Helm

The Helm chart `superset/superset:0.14.2` was used. The `SECRET_KEY` is set via the `extraSecretEnv.SUPERSET_SECRET_KEY` parameter in `values.yaml`, which populates the `superset-env` Kubernetes Secret.

1.  **Add Superset Helm Repository:**
    ```bash
    helm repo add superset https://apache.github.io/superset
    helm repo update
    ```

2.  **Prepare `superset-values.yaml`:**
    *(File: `../components/05-superset/superset-values.yaml`)*
    ```yaml
    # superset-values.yaml
    envFromSecret: "superset-env"

    extraSecretEnv:
      SUPERSET_SECRET_KEY: 'YOUR_VERY_STRONG_RANDOM_SECRET_KEY_HERE' # REPLACE THIS!

    image:
      repository: "harbor.k8s.example.internal/bigdata/superset-with-psycopg2"
      tag: "4.1.2"
      pullPolicy: IfNotPresent

    postgresql:
      enabled: true
      persistence: { enabled: true }
      auth:
        username: "superset" # Ensure these match your expectations or
        password: "dbpassword" # what superset-env might be populated with by the chart
        database: "superset" # for these values. Use strong passwords.

    redis:
      enabled: true

    # ... (supersetNode, supersetWorker, supersetCeleryBeat resources as before) ...

    ingress:
      enabled: true
      ingressClassName: "traefik"
      hosts:
        - "superset.k8s.example.internal" # Your hostname
      path: /
      pathType: Prefix
      tls:
        - secretName: "superset-tls"
          hosts:
            - "superset.k8s.example.internal"
      annotations:
        cert-manager.io/cluster-issuer: "pki-ca" # Your ClusterIssuer

    init:
      adminUser:
        username: "admin"
        password: "CHANGE_THIS_STRONG_PASSWORD" # !!! CHANGE THIS !!!
        firstname: "Admin"
        lastname: "User"
        email: "admin@example.com" # Your admin email
    ```
    *Replace placeholders like `YOUR_VERY_STRONG_RANDOM_SECRET_KEY_HERE`, `dbpassword`, `CHANGE_THIS_STRONG_PASSWORD`, `superset.k8s.example.internal`, `admin@example.com` with appropriate secure values and your specific FQDNs.*

3.  **Optional: Manually manage `superset-env` Secret if needed:**
    While `extraSecretEnv` should handle `SUPERSET_SECRET_KEY`, if other variables in `superset-env` are not correctly set by the chart based on sub-chart values (e.g., if Postgres/Redis are external or have complex auth), you might need to create/manage parts of `superset-env` manually. For our setup with bundled dependencies and `extraSecretEnv`, Helm should manage `superset-env` creation/update sufficiently.
    If manual creation was needed (as a fallback during troubleshooting):
    ```bash
    # kubectl delete secret superset-env -n superset # If resetting
    # kubectl create secret generic superset-env -n superset \
    #   --from-literal=SUPERSET_SECRET_KEY='YOUR_ACTUAL_KEY' \
    #   --from-literal=DB_HOST='superset-postgresql' \
    #   --from-literal=DB_USER='superset' \
    #   # ... other necessary env vars from previous successful attempts
    ```
    *However, relying on `extraSecretEnv` is preferred if it works for `SUPERSET_SECRET_KEY`.*

4.  **Install/Upgrade Superset:**
    Chart version `0.14.2` corresponds to App Version `4.1.2`.
    ```bash
    helm upgrade --install superset superset/superset \
      --namespace superset \
      -f ../components/05-superset/superset-values.yaml \
      --version 0.14.2
    ```
    *Using `upgrade --install` handles both initial install and subsequent upgrades.*

5.  **Force Pod Restart (If Necessary After Upgrade/Secret Change):**
    To ensure all components pick up the latest `superset-env` Secret and image:
    ```bash
    kubectl delete pod -n superset -l release=superset
    ```

6.  **Verify Deployment and Access:**
    ```bash
    kubectl get pods -n superset -w
    # Check init-db completes, web/worker/postgres/redis are Running.
    kubectl get ingress superset -n superset
    kubectl get certificate superset-tls -n superset
    ```
    Access `https://superset.k8s.example.internal/`. Log in and **change the admin password.**

## Troubleshooting Summary for Superset

*   **`insecure SECRET_KEY`:** Resolved by using `extraSecretEnv.SUPERSET_SECRET_KEY` in `values.yaml`.
*   **`No module named 'psycopg2'`:** Resolved with a custom Docker image.

## Conclusion

*(Content as previously defined)*

---
*Next Article: [Article 6: Setting up Apache Airflow for Workflow Orchestration](./06-airflow-setup.md)*
