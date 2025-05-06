# Kubernetes Big Data Stack Deployment (k8s-big-data-stack)

## Overview

This repository documents the step-by-step process of deploying and configuring a modern Big Data analytics stack on a Kubernetes cluster (`k8s.example.internal`). The goal is to build a functional platform suitable for learning, experimentation, and testing various data processing and analysis workloads.

This documentation is based on a real-world deployment scenario, detailing the investigation, choices made, and troubleshooting steps encountered.

## Target Architecture

Based on an initial survey of the provided Kubernetes cluster, which includes components like Minio (S3), Longhorn (Block Storage), Traefik, Cert-Manager, and Prometheus monitoring, the following target architecture was chosen for the Big Data stack:

1.  **Minio:** Serves as the **Data Lake** storage layer, holding raw data, intermediate results, and processed data, often in formats like Parquet or Delta Lake.
2.  **PostgreSQL:** Used as the backend database for the **Hive Metastore** and potentially for storing smaller relational datasets or aggregated results. A dedicated instance will be deployed within the `bigdata` namespace.
3.  **Apache Hive Metastore:** Acts as the central **metadata repository**, storing schemas and table definitions for data residing in Minio. This allows compute engines to understand the structure of the data lake.
4.  **Apache Spark:** The primary engine for **batch processing, ETL/ELT**, complex data transformations, and **machine learning** tasks. It will read from and write to Minio and interact with the Hive Metastore. Managed via the Spark Operator.
5.  **Trino (formerly PrestoSQL):** A high-performance, distributed **SQL query engine** for **interactive analytics**. It will query data directly from Minio (using Hive Metastore metadata) and potentially other connected sources (like PostgreSQL). It serves as the main query layer for BI tools.
6.  **BI Tool (e.g., Apache Superset / Power BI):** Connects to **Trino** (or potentially PostgreSQL for specific datasets) for data visualization, exploration, and dashboarding.

[Basic Architecture Diagram (Conceptual)](articles/images/BasicArchitectureDiagram.png)

## Repository Structure

*   **/articles**: Contains step-by-step guides and documentation in Markdown format, detailing each phase of the deployment.
    *   `01-initial-survey-and-stack-selection.md`: This document.
    *   *(Subsequent articles will cover PostgreSQL, Hive Metastore, Trino, Spark, etc.)*
    *   `images/`: Supporting images for the articles.
*   **/components**: Contains Kubernetes YAML manifests and Helm values files used for deploying each component of the stack. Subdirectories are numbered to suggest a deployment order.
    *   `00-namespace-rbac/`: Namespace creation and RBAC setup.
    *   `01-postgresql/`: Manifests for deploying PostgreSQL using a StatefulSet.
    *   `02-hive-metastore/`: Helm values for deploying Hive Metastore.
    *   `03-trino/`: Helm values and manual Ingress manifest for Trino.
    *   `04-spark/`: Spark Operator configuration and example SparkApplication manifests.
    *   *(Potentially `05-superset/` or similar for BI tools)*
*   **/scripts**: (Optional) Helper scripts for tasks like fetching secrets, running tests, etc.
*   `.gitignore`: Standard gitignore for Python, Kubernetes, Helm, etc.
*   `README.md`: This file - an overview of the project.

## Prerequisites

Before starting the deployment process described in the articles, ensure you have:

1.  **kubectl:** Installed and configured with access to the target Kubernetes cluster (`k8s.example.internal`).
2.  **Helm:** Version 3+ installed.
3.  **Git:** For cloning this repository and potentially managing configurations.
4.  **Access Credentials:** `kubeconfig` file for the cluster.
5.  **(Optional) Docker:** For building custom images or running CLI tools like Trino CLI.
6.  **(Optional) Access to Internal Git:** Access to `<internal-git-server-url>/org/k8s/dashboard` as mentioned by the administrator for cluster configuration details.

## Getting Started

To deploy this stack, follow the articles in the `/articles` directory in numerical order. Each article corresponds to a step in setting up the infrastructure and deploying a component, referencing the necessary files in the `/components` directory.

1.  **Start with:** [Article 1: Initial Kubernetes Cluster Survey and Big Data Stack Selection](./articles/01-initial-survey-and-stack-selection.md) 
2.  **Proceed to:** [Article 2: Setting up PostgreSQL and Hive Metastore](./articles/02-postgresql-hive-metastore-setup.md) 
3.  ... and so on.

## Disclaimer

This repository documents a specific deployment journey on a particular cluster configuration. While the steps and configurations can serve as a valuable reference, they might require adjustments for different Kubernetes environments, versions, or specific requirements. Use this as a guide and adapt as needed. This configuration is intended for learning/testing and may not be suitable for production without further hardening and optimization.
