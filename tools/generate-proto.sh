#!/usr/bin/env bash
set -euo pipefail

PROTO_DIR="shared/proto"
PYTHON_OUT="shared/python/shared/generated"
TS_OUT="shared/typescript/src/generated"

echo "Generating gRPC stubs from proto files..."

# Create output directories
mkdir -p "$PYTHON_OUT"
mkdir -p "$TS_OUT"

# Generate Python stubs
echo "  -> Python stubs..."
python -m grpc_tools.protoc \
  --proto_path="$PROTO_DIR" \
  --python_out="$PYTHON_OUT" \
  --pyi_out="$PYTHON_OUT" \
  --grpc_python_out="$PYTHON_OUT" \
  "$PROTO_DIR"/*.proto

# Create __init__.py for generated package
touch "$PYTHON_OUT/__init__.py"

# Fix relative imports in generated files (grpc_tools generates absolute imports)
for f in "$PYTHON_OUT"/*_pb2_grpc.py; do
  if [ -f "$f" ]; then
    sed -i.bak 's/^import \(.*\)_pb2/from . import \1_pb2/' "$f"
    rm -f "$f.bak"
  fi
done

echo "  -> Python stubs generated at $PYTHON_OUT"

# Generate TypeScript stubs (requires grpc_tools_node_protoc_ts)
if command -v grpc_tools_node_protoc_plugin &>/dev/null; then
  echo "  -> TypeScript stubs..."
  grpc_tools_node_protoc \
    --proto_path="$PROTO_DIR" \
    --js_out="import_style=commonjs,binary:$TS_OUT" \
    --grpc_out="grpc_js:$TS_OUT" \
    --ts_out="grpc_js:$TS_OUT" \
    "$PROTO_DIR"/*.proto
  echo "  -> TypeScript stubs generated at $TS_OUT"
else
  echo "  -> Skipping TypeScript stubs (grpc_tools_node_protoc not found)"
  echo "     Install: npm install -g grpc-tools grpc_tools_node_protoc_ts"
fi

echo "Done."
