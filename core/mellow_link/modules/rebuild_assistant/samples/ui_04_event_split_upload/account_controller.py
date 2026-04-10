class AccountController:
    def load_account(self, account_id, view_mode):
        route_path = "/api/accounts/detail"
        return render_account(account_id, view_mode, route_path)

