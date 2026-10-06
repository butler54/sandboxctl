"""OpenShell provider profiles managed by sandboxctl."""

from __future__ import annotations

# OpenShell 0.1 no longer ships the Vertex profile with the local gateway. Keep
# this profile in sync with OpenShell's documented google-vertex-ai profile so
# --from-gcloud-adc has the credential schema it requires.
GOOGLE_VERTEX_AI_PROFILE = """\
id: google-vertex-ai
display_name: Google Vertex AI
description: Google Vertex AI inference provider
category: inference
inference_capable: true
credentials:
  - name: service_account_key
    env_vars: [GOOGLE_SERVICE_ACCOUNT_KEY]
    required: false
  - name: service_account_token
    env_vars: [GOOGLE_VERTEX_AI_SERVICE_ACCOUNT_TOKEN, VERTEX_AI_SERVICE_ACCOUNT_TOKEN]
    required: false
    auth_style: bearer
    header_name: authorization
  - name: gcloud_adc_token
    env_vars: [GOOGLE_VERTEX_AI_TOKEN, VERTEX_AI_TOKEN]
    required: false
    auth_style: bearer
    header_name: authorization
    refresh:
      strategy: oauth2_refresh_token
      token_url: https://oauth2.googleapis.com/token
      scopes: [https://www.googleapis.com/auth/cloud-platform]
      refresh_before_seconds: 300
      max_lifetime_seconds: 3600
      material:
        - name: client_id
          required: true
        - name: client_secret
          required: true
          secret: true
        - name: refresh_token
          required: true
          secret: true
discovery:
  credentials: [service_account_token, gcloud_adc_token]
endpoints:
  - host: "*-aiplatform.googleapis.com"
    port: 443
    protocol: rest
    access: read-write
    enforcement: enforce
  - host: aiplatform.googleapis.com
    port: 443
    protocol: rest
    access: read-write
    enforcement: enforce
  - host: aiplatform.us.rep.googleapis.com
    port: 443
    protocol: rest
    access: read-write
    enforcement: enforce
  - host: aiplatform.eu.rep.googleapis.com
    port: 443
    protocol: rest
    access: read-write
    enforcement: enforce
"""
