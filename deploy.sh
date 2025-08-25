if [ "$VERCEL_GIT_COMMIT_REF" = "main" ]; then
  exit 1  # build
else
  exit 0  # skip build
fi
