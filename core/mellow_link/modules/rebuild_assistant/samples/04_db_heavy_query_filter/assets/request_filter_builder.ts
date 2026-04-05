type SearchParams = {
  category?: string;
  keyword?: string;
  startDate?: string;
  endDate?: string;
  requesterId?: string;
  includeHidden?: boolean;
};

export function buildRequestFilter(params: SearchParams, currentUserId: string) {
  const filters: string[] = [];

  if (params.category) {
    filters.push(`category = '${params.category}'`);
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

  if (!params.includeHidden) {
    filters.push(`hidden_flag = 'N'`);
  }

  return filters;
}
