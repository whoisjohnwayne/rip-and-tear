#!/bin/bash
# build-and-push.sh - Build and push Rip and Tear Docker image

set -e

# Configuration
REGISTRY="${REGISTRY:-ghcr.io}"
USERNAME="${USERNAME:-your-username}"
IMAGE_NAME="${IMAGE_NAME:-rip-and-tear}"
TAG="${TAG:-latest}"

FULL_IMAGE_NAME="${REGISTRY}/${USERNAME}/${IMAGE_NAME}:${TAG}"

echo "🔨 Building Rip and Tear Docker image..."
echo "Image: ${FULL_IMAGE_NAME}"
echo

# Build the image
docker build -t "${FULL_IMAGE_NAME}" .

echo
echo "✅ Build complete!"
echo

# Ask if user wants to push
read -p "Push to registry? (y/N): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "🚀 Pushing to registry..."
    docker push "${FULL_IMAGE_NAME}"
    echo
    echo "✅ Push complete!"
    echo
    echo "📋 For Portainer deployment, use this image name:"
    echo "   ${FULL_IMAGE_NAME}"
    echo
    echo "📖 See PORTAINER_DEPLOYMENT.md for full instructions"
else
    echo "ℹ️  Image built locally only"
    echo
    echo "To push later, run:"
    echo "   docker push ${FULL_IMAGE_NAME}"
fi

echo
echo "🎉 Ready for deployment!"
