# Terraform State Bucket Migration Guide

## Overview
Migrating Terraform state from `hit8-hit8-poc-prd-tfstate` to `hit8-poc-prd-tfstate`.

## Prerequisites
- Access to GCP project `hit8-poc`
- `gcloud` CLI installed and authenticated
- `gsutil` installed (comes with gcloud)

## Migration Steps

### 1. Create the New Bucket
First, create the new bucket with the same configuration as the old one:

```bash
# Set project
gcloud config set project hit8-poc

# Create new bucket with versioning enabled (required for state locking)
gsutil mb -p hit8-poc -c STANDARD -l europe-west1 gs://hit8-poc-prd-tfstate

# Enable versioning (required for Terraform state locking)
gsutil versioning set on gs://hit8-poc-prd-tfstate

# Set uniform bucket-level access
gsutil uniformbucketlevelaccess set on gs://hit8-poc-prd-tfstate

# Set lifecycle rule to keep last 10 versions (OPTIONAL - Terraform will manage this)
# You can skip this step if you prefer Terraform to manage the lifecycle rule
# Create a temporary lifecycle config file
cat > /tmp/lifecycle.json <<EOF
{
  "lifecycle": {
    "rule": [
      {
        "action": {"type": "Delete"},
        "condition": {"numNewerVersions": 10}
      }
    ]
  }
}
EOF

# Apply the lifecycle rule
gsutil lifecycle set /tmp/lifecycle.json gs://hit8-poc-prd-tfstate

# Clean up temporary file
rm /tmp/lifecycle.json
```

### 2. Set Up IAM Permissions
Grant yourself (or the service account Terraform uses) the necessary permissions to read/write state files:

```bash
# Get your current user email (or use the service account email)
# For user account:
YOUR_EMAIL=$(gcloud config get-value account)

# Grant Storage Object Admin role (full read/write access to objects)
gsutil iam ch user:${YOUR_EMAIL}:roles/storage.objectAdmin gs://hit8-poc-prd-tfstate

# Alternative: Grant specific permissions if you prefer least privilege
# Storage Object Viewer (read) + Storage Object Creator (write)
# gsutil iam ch user:${YOUR_EMAIL}:roles/storage.objectViewer gs://hit8-poc-prd-tfstate
# gsutil iam ch user:${YOUR_EMAIL}:roles/storage.objectCreator gs://hit8-poc-prd-tfstate

# Verify permissions
gsutil iam get gs://hit8-poc-prd-tfstate
```

**Note**: If you're using a service account for Terraform, replace `user:${YOUR_EMAIL}` with `serviceAccount:SERVICE_ACCOUNT_EMAIL`.

### 3. Copy All State Files
Copy all objects from the old bucket to the new bucket:

```bash
# Copy all objects preserving metadata
# Note: Quote the source path to prevent shell glob expansion in zsh/bash
gsutil -m cp -r "gs://hit8-hit8-poc-prd-tfstate/*" gs://hit8-poc-prd-tfstate/

# Alternative: Copy without wildcard (copies entire bucket contents)
gsutil -m cp -r gs://hit8-hit8-poc-prd-tfstate gs://hit8-poc-prd-tfstate/

# Verify the copy
gsutil ls -r gs://hit8-poc-prd-tfstate/
```

### 4. Verify State Files Were Copied
Before proceeding, verify that the state files are in the new bucket:

```bash
# List state files in new bucket
gsutil ls -r gs://hit8-poc-prd-tfstate/terraform/state/

# Compare with old bucket (should show same files)
gsutil ls -r gs://hit8-hit8-poc-prd-tfstate/terraform/state/
```

Both should show the same files (typically `default.tfstate` and possibly `default.tfstate.backup`).

### 5. Update Terraform Backend Configuration
The `backend.tf` file has already been updated to use the new bucket name:
- Old: `hit8-hit8-poc-prd-tfstate`
- New: `hit8-poc-prd-tfstate`

### 6. Re-initialize Terraform Backend
Since we've already manually copied the state files, we can re-initialize without the migration flag:

```bash
cd infra

# Re-initialize the backend (state is already in the new bucket)
terraform init -reconfigure
```

**Note**: If `terraform init -migrate-state` crashes (known Terraform bug), use the manual copy approach above and then run `terraform init -reconfigure` instead.

### 7. Import the New Bucket into Terraform State
Since we manually created the new bucket, we need to import it into Terraform state. First, we need to remove the old bucket from Terraform state, then import the new one:

```bash
# Step 1: Remove the old bucket from Terraform state (doesn't delete the actual bucket)
terraform state rm google_storage_bucket.terraform_state

# Step 2: Import the new bucket
terraform import google_storage_bucket.terraform_state hit8-poc-prd-tfstate

# Step 3: Verify the import - should show the new bucket name
terraform state show google_storage_bucket.terraform_state | grep "name ="
```

**Important**: 
- Removing from state doesn't delete the actual bucket in GCS
- The old bucket (`hit8-hit8-poc-prd-tfstate`) will still exist in GCS but won't be managed by Terraform
- The new bucket (`hit8-poc-prd-tfstate`) will now be managed by Terraform

### 8. Verify State Migration
Verify that Terraform can read the state from the new bucket:

```bash
# Check that Terraform can access the state
terraform state list

# Verify the state is correct
terraform plan
```

The `terraform plan` should show no changes (or only expected changes), confirming that the state was migrated correctly.

### 9. Verify State File Location
Confirm the state is in the new bucket:

```bash
# List state files in new bucket
gsutil ls gs://hit8-poc-prd-tfstate/terraform/state/

# Compare with old bucket (should be identical)
gsutil ls gs://hit8-hit8-poc-prd-tfstate/terraform/state/
```

### 10. (Optional) Delete Old Bucket
Once you've verified everything works correctly, you can delete the old bucket:

```bash
# First, verify the new bucket has all the state files
gsutil ls -r gs://hit8-poc-prd-tfstate/terraform/state/

# Delete all objects in the old bucket
gsutil -m rm -r gs://hit8-hit8-poc-prd-tfstate/*

# Delete the old bucket
gsutil rb gs://hit8-hit8-poc-prd-tfstate
```

**Warning**: Only delete the old bucket after confirming:
- Terraform operations work correctly with the new bucket
- All state files are present in the new bucket
- You have a backup if needed

## Troubleshooting

### If `terraform init -migrate-state` crashes:
This is a known Terraform bug. Use the manual migration approach:
1. Manually copy state files using `gsutil` (as shown in step 2)
2. Use `terraform init -reconfigure` instead of `terraform init -migrate-state`
3. Verify state is accessible with `terraform state list`

### If you get "Access denied" (403) errors:
1. **Grant IAM permissions** on the new bucket:
   ```bash
   YOUR_EMAIL=$(gcloud config get-value account)
   gsutil iam ch user:${YOUR_EMAIL}:roles/storage.objectAdmin gs://hit8-poc-prd-tfstate
   ```
2. Verify permissions: `gsutil iam get gs://hit8-poc-prd-tfstate`
3. Test access: `gsutil ls gs://hit8-poc-prd-tfstate/terraform/state/`
4. If using a service account, grant permissions to that service account instead

### If `terraform init` fails:
1. Ensure the new bucket exists and has versioning enabled
2. **Verify you have read/write access to the new bucket** (see above)
3. Check that the state files were copied to the correct path: `gs://hit8-poc-prd-tfstate/terraform/state/`
4. Verify the state file name matches what Terraform expects (usually `default.tfstate`)
5. Test bucket access: `gsutil ls gs://hit8-poc-prd-tfstate/`

### If state appears empty after migration:
1. Verify the state files were copied to the correct path: `gs://hit8-poc-prd-tfstate/terraform/state/`
2. Check the state file name matches what Terraform expects (usually `default.tfstate`)
3. Try manually copying the state file again

### Rollback (if needed):
If something goes wrong, you can rollback by:
1. Reverting `backend.tf` to use the old bucket name: `hit8-hit8-poc-prd-tfstate`
2. Running `terraform init -reconfigure` to switch back to the old backend
3. Verify state is accessible: `terraform state list`

## Notes
- The old bucket (`hit8-hit8-poc-prd-tfstate`) should not be deleted until you're 100% certain the migration was successful
- Keep the old bucket for at least a few days as a backup
- The chat buckets (`hit8-hit8-poc-dev-chat` and `hit8-hit8-poc-prd-chat`) can be deleted manually as they don't contain Terraform state
