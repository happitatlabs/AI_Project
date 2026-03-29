// C# Amount Limit Example
public class ExpensePolicyService
{
    public string EvaluateExpense(decimal amount, decimal dailyLimit, bool isExecutive)
    {
        if (amount <= 0)
        {
            return "INVALID";
        }

        if (isExecutive && amount <= 300000)
        {
            return "AUTO_APPROVED";
        }

        if (amount <= dailyLimit)
        {
            return "WITHIN_LIMIT";
        }

        if (amount > dailyLimit && amount <= 1000000)
        {
            return "REQUIRES_MANAGER_APPROVAL";
        }

        return "REQUIRES_FINANCE_APPROVAL";
    }
}
