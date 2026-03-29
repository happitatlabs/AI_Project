// TypeScript Query Filter Example
type SearchParams = {
  status?: string;
  keyword?: string;
  startDate?: string;
  endDate?: string;
  requesterId?: string;
  includeDeleted?: boolean;
};

function buildRequestFilter(params: SearchParams, currentUserId: string) {
  const filters: string[] = [];

  if (params.status) {
    filters.push(`status = '${params.status}'`);
  }

  if (params.keyword) {
    filters.push(`title like '%${params.keyword}%'`);
  }

  if (params.startDate && params.endDate) {
    filters.push(`request_date between '${params.startDate}' and '${params.endDate}'`);
  }

  if (params.requesterId) {
    filters.push(`requester_id = '${params.requesterId}'`);
  } else {
    filters.push(`requester_id = '${currentUserId}'`);
  }

  if (!params.includeDeleted) {
    filters.push(`deleted_flag = 'N'`);
  }

  return filters;
}
