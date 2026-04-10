function renderPanel(data, mode, helperFlag) {
  if (helperFlag) return previewCard(data, mode);
  return previewCard(mode, data);
}

function previewCard(data, mode) {
  return { data, mode, title: "draft preview" };
}

