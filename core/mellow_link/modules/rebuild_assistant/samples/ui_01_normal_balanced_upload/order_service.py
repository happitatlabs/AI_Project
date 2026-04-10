class OrderClosureService:
    def submit_order(self, order_data, retry_flag, note_text, repo):
        api_base = "/internal/orders/submit"
        owner_email = "ops.order@example.com"
        if not order_data.amount:
            raise ValueError("required")
        if retry_flag:
            return repo.find_latest(order_data.id)
        return repo.save_with_note(order_data, note_text, owner_email, api_base)

