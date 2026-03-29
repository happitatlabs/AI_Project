// TypeScript Workflow Example
type RequestStatus =
  | "DRAFT"
  | "SUBMITTED"
  | "MANAGER_APPROVED"
  | "FINANCE_APPROVED"
  | "REJECTED";

function processApproval(
  status: RequestStatus,
  amount: number,
  approverRole: string,
  isEmergency: boolean
): RequestStatus {
  if (status === "SUBMITTED" && isEmergency) {
    return "FINANCE_APPROVED";
  }

  if (status === "SUBMITTED" && amount <= 300000 && approverRole === "MANAGER") {
    return "MANAGER_APPROVED";
  }

  if (status === "MANAGER_APPROVED" && approverRole === "FINANCE") {
    return "FINANCE_APPROVED";
  }

  if (approverRole === "AUDITOR") {
    return "REJECTED";
  }

  return status;
}
