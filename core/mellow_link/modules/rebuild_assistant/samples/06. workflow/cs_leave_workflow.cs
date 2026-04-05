// C# Workflow Example
public class LeaveApprovalFlow
{
    public string GetNextStep(int leaveDays, bool isTeamLead, bool hasDelegate, string currentStatus)
    {
        if (currentStatus == "REQUESTED" && leaveDays <= 3)
        {
            return "TEAM_LEAD_APPROVAL";
        }

        if (currentStatus == "REQUESTED" && leaveDays > 3)
        {
            return "HR_APPROVAL";
        }

        if (currentStatus == "TEAM_LEAD_APPROVAL" && hasDelegate)
        {
            return "APPROVED";
        }

        if (currentStatus == "TEAM_LEAD_APPROVAL" && !hasDelegate)
        {
            return "PENDING_DELEGATE_ASSIGNMENT";
        }

        if (currentStatus == "HR_APPROVAL" && isTeamLead)
        {
            return "DIRECTOR_APPROVAL";
        }

        return currentStatus;
    }
}
