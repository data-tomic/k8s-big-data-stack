# Kubernetes Big Data Stack Deployment (k8s-big-data-stack)

## Overview

This repository documents the step-by-step process of deploying and configuring a modern Big Data analytics stack on a Kubernetes cluster (using `k8s.example.internal` as a placeholder FQDN). The goal is to build a functional platform suitable for learning, experimentation, and testing various data processing and analysis workloads.

This documentation is based on a real-world deployment scenario, detailing the investigation, choices made, and troubleshooting steps encountered.

## Target Architecture

Based on an initial survey of the provided Kubernetes cluster, which includes components like Minio (S3), Longhorn (Block Storage), Traefik, Cert-Manager, and Prometheus monitoring, the following target architecture was chosen for the Big Data stack:

1.  **Minio:** Serves as the **Data Lake** storage layer.
2.  **PostgreSQL:** Backend for the **Hive Metastore**.
3.  **Apache Hive Metastore:** Central **metadata repository**.
4.  **Apache Spark:** Engine for **batch processing, ETL/ELT**, managed via the Spark Operator.
5.  **Trino (formerly PrestoSQL):** Distributed **SQL query engine** for **interactive analytics**.
6.  **Apache Superset:** Business Intelligence tool for **data visualization and exploration**.
7.  **(Upcoming) Apache Airflow:** Workflow orchestration and scheduling.

[Basic Architecture Diagram (Conceptual)](./articles/images/BasicArchitectureDiagram.png)

## Repository Structure

*   **/articles**: Contains step-by-step guides and documentation in Markdown format.
    *   `images/`: Supporting images for the articles.
*   **/components**: Contains Kubernetes YAML manifests and Helm values files.
    *   `00-namespace-rbac/`: Namespace creation and RBAC.
    *   `01-postgresql/`: PostgreSQL deployment.
    *   `02-hive-metastore/`: Hive Metastore Helm configuration.
    *   `03-trino/`: Trino Helm configuration and Ingress.
    *   `04-spark/`: Spark Operator, RBAC, custom image, and example jobs.
    *   `05-superset/`: Superset custom image and Helm configuration.
    *   *(Upcoming `06-airflow/`)*
*   **/scripts**: (Optional) Helper scripts.
*   `README.md`: This overview file.

## Prerequisites

Before starting, ensure you have:

1.  **kubectl:** Installed and configured for your target Kubernetes cluster.
2.  **Helm:** Version 3+ installed.
3.  **Git:** For cloning this repository.
4.  **Docker:** For building custom images (e.g., for Spark and Superset).
5.  **Access Credentials:** `kubeconfig` for the cluster, credentials for your private Docker registry (e.g., Harbor).

## Getting Started

To deploy this stack, follow the articles in the `/articles` directory in numerical order. Each article corresponds to a step in setting up the infrastructure and deploying a component, referencing the necessary files in the `/components` directory.

**Deployment Order & Articles:**

1.  **Initial Setup & Planning:**
    *   [Article 1: Initial Kubernetes Cluster Survey and Big Data Stack Selection](./articles/01-initial-survey-and-stack-selection.md)
2.  **Metadata Layer:**
    *   [Article 2: Setting up PostgreSQL and Hive Metastore](./articles/02-postgresql-hive-metastore-setup.md)
3.  **Interactive Query Engine:**
    *   [Article 3: Deploying and Configuring Trino](./articles/03-trino-setup-and-integration.md)
4.  **Batch Processing Engine:**
    *   [Article 4: Setting up Spark Operator and Running Spark Jobs](./articles/04-spark-operator-and-jobs.md)
5.  **Business Intelligence & Visualization:**
    *   [Article 5: Deploying Apache Superset for Business Intelligence](./articles/05-superset-deployment.md)
6.  **(Upcoming) Workflow Orchestration:**
    *   *Article 6: Setting up Apache Airflow for Workflow Orchestration (Link to be created)*
7.  **(Upcoming) End-to-End Example:**
    *   *Article 7: Building and Running an End-to-End Data Pipeline (Link to be created)*

Start with Article 1 and proceed sequentially. Each article builds upon the previous ones.

## Disclaimer

This repository documents a specific deployment journey on a particular cluster configuration. While the steps and configurations can serve as a valuable reference, they might require adjustments for different Kubernetes environments, versions, or specific requirements. Use this as a guide and adapt as needed. This configuration is intended for learning/testing and may not be suitable for production without further hardening and optimization.
