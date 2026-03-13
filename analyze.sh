#!/bin/bash
set -e

# Fetch target branch and generate diff
git fetch origin $CI_MERGE_REQUEST_TARGET_BRANCH_NAME
git diff origin/$CI_MERGE_REQUEST_TARGET_BRANCH_NAME...HEAD > pr.diff

# Check if diff is empty
if [ ! -s pr.diff ]; then
  echo "No code changes detected in this MR. Skipping analysis."
  exit 0
fi

# Build payload
python3 << 'EOF'
import json, os
payload = {
    'diff': open('pr.diff').read(),
    'pr_title': os.environ.get('CI_MERGE_REQUEST_TITLE', ''),
    'repo': os.environ.get('CI_PROJECT_PATH', ''),
    'pr_number': int(os.environ.get('CI_MERGE_REQUEST_IID', 0))
}
open('payload.json', 'w').write(json.dumps(payload))
EOF

# Call API
RESPONSE=$(curl -s -X POST "${API_GATEWAY_URL}" -H "Content-Type: application/json" -d @payload.json)
echo "API Response: ${RESPONSE}"

# Parse response and post MR comment
NOTE=$(python3 << EOF
import json, sys

response = json.loads('''${RESPONSE}''')
body = json.loads(response['body'])

tag      = body.get('modification_tag', '')
summary  = body.get('summary', '')
risks    = '\n'.join(f"- {r}" for r in body.get('risk_notes', []))
checklist = '\n'.join(f"- [ ] {t}" for t in body.get('test_checklist', []))

print(f"**Tag:** {tag}\n\n**Summary:** {summary}\n\n**Risks:**\n{risks}\n\n**Test Checklist:**\n{checklist}")
EOF
)

curl -s --request POST \
    "${CI_API_V4_URL}/projects/${CI_PROJECT_ID}/merge_requests/${CI_MERGE_REQUEST_IID}/notes" \
    --header "PRIVATE-TOKEN: ${GITLAB_TOKEN}" \
    --data-urlencode "body=${NOTE}"
