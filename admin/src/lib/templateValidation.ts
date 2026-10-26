type TemplateValidationInput = {
  id: string; name: string; preview_cover: string; default_ratio: string;
  shot_duration_min: number; shot_duration_max: number; sort_order: number;
};

export function validateTemplate(form: TemplateValidationInput): string | null {
  if (!form.id.trim() || form.id.trim().length > 64) return "模板 ID 必填，且不能超过 64 个字符";
  if (!form.name.trim() || form.name.trim().length > 128) return "模板名称必填，且不能超过 128 个字符";
  if (!["16:9", "9:16", "1:1", "4:3", "3:4"].includes(form.default_ratio)) return "请选择有效的默认画幅";
  if (![form.shot_duration_min, form.shot_duration_max, form.sort_order].every(Number.isSafeInteger)) return "排序与镜头时长必须为有效整数";
  if (form.shot_duration_min <= 0 || form.shot_duration_max < form.shot_duration_min) return "镜头时长必须大于 0，且最大时长不能小于最小时长";
  const cover = form.preview_cover.trim();
  if (cover && !cover.startsWith("/")) {
    try { if (!["http:", "https:"].includes(new URL(cover).protocol)) return "封面应使用 HTTP(S) 地址或 / 开头的相对路径"; }
    catch { return "封面应使用 HTTP(S) 地址或 / 开头的相对路径"; }
  }
  if (cover.startsWith("//")) return "相对封面路径请使用单个 / 开头";
  return null;
}
