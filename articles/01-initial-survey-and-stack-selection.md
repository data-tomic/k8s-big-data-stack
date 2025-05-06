```markdown
# Article 1: Initial Kubernetes Cluster Survey and Big Data Stack Selection

*Date: 2025-05-05*

## Introduction

Recently, I was given access to a pre-configured Kubernetes cluster running Talos Linux (`k8s.example.internal`). The goal of this series of articles is to document the process of deploying and configuring a modern Big Data analytics stack on this cluster. In this first article, we will perform an initial survey of the existing cluster components and, based on that, choose the target architecture for our Big Data stack.

## Step 1: Initial Connection and Tool Setup

The first step was to gain access to the cluster. The administrators provided a `kubeconfig` file containing all necessary credentials and endpoints.

To interact with the cluster, the `kubectl` utility is required. On my workstation (Ubuntu), it was installed using the current official Kubernetes repositories:

```bash
# Clean up old/failed install attempts (if any)
# sudo rm /etc/apt/sources.list.d/kubernetes.list
# sudo apt-get update

# Install dependencies
sudo apt-get update
sudo apt-get install -y apt-transport-https ca-certificates curl gpg

# Add Kubernetes v1.30 repository key and source (example)
sudo mkdir -p -m 755 /etc/apt/keyrings
curl -fsSL https://pkgs.k8s.io/core:/stable:/v1.30/deb/Release.key | sudo gpg --dearmor -o /etc/apt/keyrings/kubernetes-apt-keyring.gpg
echo 'deb [signed-by=/etc/apt/keyrings/kubernetes-apt-keyring.gpg] https://pkgs.k8s.io/core:/stable:/v1.30/deb/ /' | sudo tee /etc/apt/sources.list.d/kubernetes.list

# Install kubectl
sudo apt-get update
sudo apt-get install -y kubectl

# Verify installation
kubectl version --client
```

After installing `kubectl`, the provided `kubeconfig` file was placed in the default location `~/.kube/config`.

A connection test to the cluster was successful:

```bash
kubectl cluster-info
kubectl get nodes
```

*(Output confirming connection and node list would typically be included here or referenced)*

## Step 2: Surveying Installed Components

To understand the current state of the cluster and the services already deployed, the `kubectl get pods -A` command was used:

```bash
kubectl get pods -A
# NAMESPACE                       NAME                                                        READY   STATUS      RESTARTS         AGE
# argocd                          argocd-application-controller-0                             1/1     Running     0                ...
# argocd                          argocd-applicationset-controller-...                        1/1     Running     0                ...
# ... (many other pods were listed, representing various services) ...
# cert-manager                    cert-manager-...                                            1/1     Running   0                ...
# flux-system                     helm-controller-...                                         1/1     Running   ...              ...
# harbor                          harbor-core-...                                             1/1     Running   0                ...
# ingress-nginx                   ingress-nginx-controller-...                                1/1     Running   0                ...
# kube-system                     cilium-...                                                  1/1     Running   0                ...
# kube-system                     coredns-...                                                 1/1     Running   ...              ...
# kubernetes-dashboard            kubernetes-dashboard-api-...                                1/1     Running   0                ...
# longhorn-system                 longhorn-manager-...                                        2/2     Running   ...              ...
# minio                           minio-...                                                   1/1     Running   0                ...
# monitoring                      kube-prometheus-stack-grafana-...                           3/3     Running   ...              ...
# monitoring                      prometheus-kube-prometheus-stack-prometheus-0               2/2     Running   0                ...
# traefik                         traefik-...                                                 1/1     Running   ...              ...
```

Analyzing the list of running pods and namespaces revealed the presence of the following key components:

*   **Networking:**
    *   **CNI:** Cilium (including Hubble for observability)
    *   **Ingress Controllers:** Traefik (actively used) and ingress-nginx (present)
    *   **DNS:** CoreDNS (standard)
    *   **Certificates:** Cert-Manager (configured with an internal CA `<internal-ca-issuer>`)
    *   **DNS Records:** External-DNS
*   **Storage:**
    *   **Block:** Longhorn (providing the `longhorn` StorageClass)
    *   **Object:** Minio (S3-compatible storage)
*   **Monitoring & Logging:**
    *   `kube-prometheus-stack`: A full stack including Prometheus, Grafana, Alertmanager, node-exporter, kube-state-metrics.
*   **CI/CD & GitOps:**
    *   Argo CD
    *   Flux CD (used for managing the cluster infrastructure itself, according to the admin's email)
*   **Image Registry:**
    *   Harbor (with integrated Trivy scanner)
*   **Management & UI:**
    *   Kubernetes Dashboard
    *   Web UIs for Grafana, Argo CD, Harbor, Longhorn, Hubble, Traefik (accessible via Ingress).

Access to the web UIs was verified using `kubectl get ingress -A`, which showed the configured hostnames under the `k8s.example.internal` domain and the Ingress IP address `<ingress-ip>` (likely the Traefik service address).

```bash
kubectl get ingress -A
# NAMESPACE              NAME                            CLASS     HOSTS                     ADDRESS         PORTS     AGE
# argocd                 argocd-server                   traefik   argocd.k8s.example.internal <ingress-ip>    80, 443   ...
# ... (other Ingresses listed, like Grafana, Harbor, Minio etc.) ...
# monitoring             kube-prometheus-stack-grafana   traefik   grafana.k8s.example.internal <ingress-ip>   80, 443   ...
# ...
```

Additionally, an issue with a stuck `kubeapps` namespace (in `Terminating` state) was identified and resolved during the initial exploration by removing a finalizer from a leftover `AppRepository` custom resource. This highlighted the presence of Helm and potentially previously installed applications.

## Step 3: Choosing the Big Data Stack Architecture

Based on the cluster survey, it became clear that it provides a powerful and modern foundation for deploying an analytics stack. The key available components relevant to a data platform are:

*   **Data Lake Storage:** Minio (S3 compatible)
*   **Metadata/Relational Storage:** PostgreSQL (available, though a dedicated instance is preferable)
*   **Orchestration:** Kubernetes with operators and GitOps tooling (Argo CD, Flux CD)
*   **Persistent Block Storage:** Longhorn

The decision was made to build a highly functional and flexible architecture capable of handling both batch processing (ETL/ELT) and interactive analytics/visualization tasks. The chosen stack consists of the following core components:

1.  **Minio:** Serves as the primary **Data Lake** storage layer, holding raw data, intermediate results, and processed data, often in formats like Parquet or Delta Lake.
2.  **PostgreSQL:** A dedicated instance will be deployed to serve as the backend database for the **Apache Hive Metastore** and potentially store smaller relational datasets or aggregated results.
3.  **Apache Hive Metastore:** Acts as the central **metadata repository**, storing schemas and table definitions for data residing in Minio. This allows compute engines to understand the structure of the data lake.
4.  **Apache Spark:** The primary engine for **batch processing, ETL/ELT**, complex data transformations, and **machine learning** tasks. It will be integrated with Hive Metastore and Minio and managed via the Spark Operator.
5.  **Trino (formerly PrestoSQL):** A high-performance, distributed **SQL query engine** for **interactive analytics**. It will query data directly from Minio (using Hive Metastore metadata) and potentially other connected sources (like PostgreSQL). It serves as the main query layer for BI tools.
6.  **BI Tool (e.g., Apache Superset / Power BI):** Connects to **Trino** (or potentially PostgreSQL for specific datasets) for data visualization, exploration, and dashboarding. *The specific BI tool choice will be addressed later.*

**Rationale for Architecture:**

*   **Separation of Concerns:** Spark handles heavy data processing, while Trino provides fast query responses for analysts and BI tools.
*   **Scalability:** Each component (Minio, Postgres, Metastore, Spark, Trino) can be scaled independently within Kubernetes.
*   **Flexibility:** Trino's federated query capabilities allow querying data across multiple sources if needed.
*   **Standards:** Utilizes widely adopted, robust open-source technologies common in the Big Data ecosystem.
*   **Leverages Existing Infrastructure:** Makes good use of the already available Minio, Longhorn, and Kubernetes orchestration capabilities.

## Conclusion and Next Steps

The initial survey confirmed that the provided Kubernetes cluster (`k8s.example.internal`) is an excellent platform for building a modern data stack. The chosen architecture (Minio, PostgreSQL, Hive Metastore, Spark, Trino) provides a solid foundation for diverse analytical workloads.

The subsequent articles in this series will document the deployment and configuration of each component:

1.  Setting up a dedicated PostgreSQL instance and deploying the Hive Metastore.
2.  Deploying and configuring Trino, ensuring its integration with Hive Metastore and Minio.
3.  Setting up the Spark Operator and running example Spark jobs to interact with the metastore and data lake.
4.  Integrating with a Business Intelligence tool.

Stay tuned for the next article where we dive into setting up PostgreSQL and Hive Metastore within our `bigdata` namespace.
