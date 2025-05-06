```markdown
# Article 3: Deploying and Configuring Trino

*Date: 2025-05-06*
*Previous Article: [Article 2: Setting up PostgreSQL and Hive Metastore](./02-postgresql-hive-metastore-setup.md)*

## Introduction

With our dedicated PostgreSQL database and Hive Metastore running in the `bigdata` namespace, we are now ready to deploy Trino, the distributed SQL query engine. Trino will serve as our primary interface for interactive analytics, querying data stored in Minio via the metadata managed by the Hive Metastore.

This article covers the installation and configuration of Trino using its official Helm chart, including troubleshooting steps encountered due to Helm chart bugs and Pod Security constraints.

## Step 1: Adding the Trino Helm Repository

The official Trino Helm charts are now distributed via GitHub Pages. We add the repository using `helm`:

```bash
# Remove previous failed attempts (if any)
helm repo remove trinodb || true
helm repo remove trino-oci || true

# Add the official repository
helm repo add trino https://trinodb.github.io/charts/

# Update repositories
helm repo update

# Verify chart availability (e.g., version 1.39.0 for Trino 475)
helm search repo trino/trino -l
```

## Step 2: Preparing Trino Configuration (`trino-values-full.yaml`)

We need to configure Trino to connect to our Hive Metastore and Minio, and also enable compatibility with our Traefik Ingress setup.

*(The final, working content of `trino-values-full.yaml` can be found here: [../components/03-trino/trino-values-full.yaml](../components/03-trino/trino-values-full.yaml) - Ensure path is correct)*

**Key Configuration Sections:**

1.  **Image:** We specify the Trino version corresponding to the chart version (e.g., tag `475` for chart `1.39.0`).
    ```yaml
    image:
      repository: trinodb/trino
      tag: "475" # Or leave empty to use chart's appVersion
      pullPolicy: IfNotPresent
    ```

2.  **Coordinator and Worker Resources:** Adjust CPU/Memory requests and limits as needed.
    ```yaml
    coordinator:
      resources:
        requests: { cpu: 1000m, memory: 2Gi }
        limits: { cpu: 2000m, memory: 4Gi }
    worker:
      replicas: 2 # Start with 2 workers
      resources:
        requests: { cpu: 1000m, memory: 2Gi }
        limits: { cpu: 2000m, memory: 4Gi }
    ```

3.  **Connectors (`catalogs` section):** This defines how Trino accesses data sources.
    *   **Hive Connector:** Configured to use our deployed Hive Metastore and Minio. Crucially, it uses the **`s3.*`** properties for native S3 support and fetches Minio credentials from environment variables.
        ```yaml
        catalogs:
          hive: |
            connector.name=hive
            hive.metastore.uri=thrift://ilum-hive-metastore.bigdata.svc.cluster.local:9083
            # --- Enable and configure Native S3 Support ---
            fs.native-s3.enabled=true
            # S3 (Minio) Parameters
            s3.endpoint=http://minio.minio.svc.cluster.local:9000
            s3.path-style-access=true
            s3.aws-access-key=${env:MINIO_ACCESS_KEY}
            s3.aws-secret-key=${env:MINIO_SECRET_KEY}
            s3.region=us-east-1 # Dummy region required by AWS SDK
          # Default catalogs for testing
          tpch: |
            connector.name=tpch
          tpcds: |
            connector.name=tpcds
        ```
    *   **Environment Variables (`envFrom`):** This top-level section injects the Minio credentials from our previously created secret into all Trino pods.
        ```yaml
        envFrom:
          - secretRef:
              name: minio-s3-secret # Kubernetes secret holding Minio keys
        ```

4.  **Additional Config Properties:** We add necessary properties to Trino's `config.properties`.
    *   `http-server.process-forwarded=true` is essential for Trino to correctly handle requests coming through the Traefik proxy/Ingress.
        ```yaml
        additionalConfigProperties:
          - "http-server.process-forwarded=true"
        ```

5.  **Ingress (Disabled in Chart):** Due to bugs encountered in the chart's Ingress template (versions 1.38.0 and 1.39.0 failed to generate valid rules), we disable Ingress creation via Helm and will create it manually later.
    ```yaml
    ingress:
      enabled: false
    ```

## Step 3: Installing Trino using Helm

With the `values.yaml` prepared, we install Trino using Helm.

```bash
# Ensure any previous failed 'trino' releases are removed
helm uninstall trino -n bigdata || true

# Install Trino using the prepared values file
helm install trino trino/trino --version 1.39.0 \
  --namespace bigdata \
  -f ../components/03-trino/trino-values-full.yaml
```

*(Note: Pod Security warnings related to `restricted:latest` might appear during client-side validation but can be ignored as the `bigdata` namespace is labeled with the `baseline` policy).*

The expected output indicates successful deployment: `STATUS: deployed`.

## Step 4: Verifying Trino Pods

After installation, we monitor the pods until the coordinator and workers are running and ready.

```bash
kubectl get pods -n bigdata -l app.kubernetes.io/name=trino -w
# NAME                                 READY   STATUS    RESTARTS   AGE
# trino-coordinator-xxxxxxxxxx-xxxxx   1/1     Running   0          ...
# trino-worker-yyyyyyyyyy-yyyyy        1/1     Running   0          ...
# trino-worker-yyyyyyyyyy-zzzzz        1/1     Running   0          ...
```

We also confirm that the Minio credentials were correctly injected:
```bash
COORD_POD=$(kubectl get pods -n bigdata -l app.kubernetes.io/name=trino,app.kubernetes.io/component=coordinator -o jsonpath='{.items[0].metadata.name}')
kubectl exec -it $COORD_POD -n bigdata -- printenv | grep MINIO
# Expected output showing MINIO_ACCESS_KEY and MINIO_SECRET_KEY
```

## Step 5: Creating Ingress Manually

Since the Helm chart's Ingress creation was problematic, we define the Ingress resource manually.

1.  **Get Coordinator Service Details:** Identify the service name and port for the Trino coordinator.
    ```bash
    kubectl get svc -n bigdata -l app.kubernetes.io/name=trino,app.kubernetes.io/component=coordinator
    # NAME    TYPE        CLUSTER-IP     EXTERNAL-IP   PORT(S)    AGE
    # trino   ClusterIP   10.x.x.x       <none>        8080/TCP   ...
    ```
    *(In this case, the service is named `trino` and listens on port `8080`).*

2.  **Create `trino-ingress.yaml` Manifest:**
    *(The content of `trino-ingress.yaml` can be found here: [../components/03-trino/trino-ingress.yaml](../components/03-trino/trino-ingress.yaml) - Ensure path is correct)*

    *Key configurations:*
    *   `metadata.namespace: bigdata`
    *   `metadata.annotations`: Includes `cert-manager.io/cluster-issuer: "<internal-ca-issuer>"` (using the correct issuer name `pki-ca` found earlier).
    *   `spec.ingressClassName: traefik`
    *   `spec.rules`: Defines routing for `trino.k8s.example.internal` to the `trino` service on port `8080`.
    *   `spec.tls`: Configures TLS using Cert-Manager to issue a certificate stored in the `trino-tls` secret.

3.  **Apply the Ingress Manifest:**
    ```bash
    kubectl apply -f ../components/03-trino/trino-ingress.yaml
    ```

4.  **Verify Ingress and Certificate:**
    ```bash
    kubectl get ingress trino-manual-ingress -n bigdata
    # Check for ADDRESS assignment

    kubectl get certificate trino-tls -n bigdata
    # Wait for READY=True
    ```

## Step 6: Final Verification (UI and CLI)

1.  **Access the UI:** Ensure `trino.k8s.example.internal` resolves to the Ingress IP (`<ingress-ip>`) via DNS or hosts file. Open `https://trino.k8s.example.internal/` in a browser. The Trino UI should load (potentially with a browser warning due to the internal CA). The version displayed should match the deployed application version (e.g., 475).

2.  **Test via CLI:** Connect using the Trino CLI (using `--insecure` for the internal CA) and verify catalog visibility.
    ```bash
    docker run -it --rm trinodb/trino trino \
      --server https://trino.k8s.example.internal \
      --user testuser \
      --insecure \
      --execute "SHOW CATALOGS;"
    ```
    *Expected output should include `hive`, `system`, `tpcds`, `tpch`.*

## Conclusion

Trino is now successfully deployed and configured within the `bigdata` namespace. It is connected to the Hive Metastore and configured to access Minio using the native S3 filesystem support. Access to the Trino UI is enabled via a manually created Ingress resource managed by Traefik and secured with TLS via Cert-Manager.

The next step is to configure and test Apache Spark, ensuring it can also interact with the Hive Metastore and Minio to read and write data.

---
*Next Article: [Article 4: Setting up Spark Operator and Running Jobs](./04-spark-operator-and-jobs.md) (Link to be created)*
