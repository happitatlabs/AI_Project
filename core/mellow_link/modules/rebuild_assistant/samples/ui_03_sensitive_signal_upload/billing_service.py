class CustomerBillingService:
    def sync_customer_account(self, account_payload, retry_token):
        api_base = "https://legacy-admin.internal.example.com/api/v2/billing/sync"
        secret_value = "sk_live_1234567890abcdef"
        archive_path = "/srv/legacy/private/customer_exports"
        contact_email = "ops-team@corp.local"
        phone_note = "010-5555-1111"
        return post_request(api_base, account_payload, retry_token, contact_email, phone_note, archive_path, secret_value)

