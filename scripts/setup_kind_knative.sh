#!/usr/bin/env bash
set -euo pipefail

CLUSTER_NAME="knative-lab"
KNATIVE_VERSION="knative-v1.13.0"

echo "[1/7] Creating kind cluster: ${CLUSTER_NAME}"

cat > kind-config.yaml <<EOF
kind: Cluster
apiVersion: kind.x-k8s.io/v1alpha4
nodes:
- role: control-plane
  extraPortMappings:
  - containerPort: 30080
    hostPort: 8080
    protocol: TCP
EOF

kind delete cluster --name "${CLUSTER_NAME}" >/dev/null 2>&1 || true
kind create cluster --name "${CLUSTER_NAME}" --config kind-config.yaml

echo "[2/7] Installing Knative Serving (${KNATIVE_VERSION})"
kubectl apply -f "https://github.com/knative/serving/releases/download/${KNATIVE_VERSION}/serving-crds.yaml"
kubectl apply -f "https://github.com/knative/serving/releases/download/${KNATIVE_VERSION}/serving-core.yaml"
kubectl wait --for=condition=Ready pods --all -n knative-serving --timeout=240s

echo "[3/7] Installing Kourier (${KNATIVE_VERSION})"
kubectl apply -f "https://github.com/knative/net-kourier/releases/download/${KNATIVE_VERSION}/kourier.yaml"
kubectl wait --for=condition=Ready pods --all -n kourier-system --timeout=240s

echo "[4/7] Configuring Knative to use Kourier ingress"
kubectl patch configmap/config-network -n knative-serving --type merge \
  -p '{"data":{"ingress-class":"kourier.ingress.networking.knative.dev"}}'

echo "[5/7] Setting domain to 127.0.0.1.sslip.io"
kubectl apply -f - <<EOF
apiVersion: v1
kind: ConfigMap
metadata:
  name: config-domain
  namespace: knative-serving
data:
  127.0.0.1.sslip.io: ""
EOF

echo "[6/7] Exposing Kourier via NodePort (mapped to host :8080)"
kubectl patch svc kourier -n kourier-system --type='merge' -p '{
  "spec": {
    "type": "NodePort",
    "ports": [
      {"name":"http2","port":80,"targetPort":8080,"nodePort":30080},
      {"name":"https","port":443,"targetPort":8443}
    ]
  }
}'

echo "[7/7] Done. Try:"
echo "  kubectl get pods -A"
echo "  kn service create hello --image gcr.io/knative-samples/helloworld-go --port 8080"
echo "  curl -H \"Host: hello.default.127.0.0.1.sslip.io\" http://127.0.0.1:8080/"
