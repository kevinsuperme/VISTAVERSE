import { useCallback, useEffect } from "react";
import { ArrowLeft } from "lucide-react";
import { Link, useLocation, useParams } from "react-router-dom";
import { useAdminRequest } from "@/hooks/useAdminRequest";
import { safeNextPath } from "@/lib/authRedirect";
import { api, type AdminDramaAsset } from "@/api/client";
import { AdminDetailMeta, AdminDetailSection } from "@/components/admin/AdminDetailLayout";
import { AdminEntityLink } from "@/components/admin/AdminEntityLink";
import { Button } from "@/components/ui/button";
import { dramaAssetTypeLabel, formatDramaGenerationStatus } from "@/lib/dramaLabels";

/** 漫剧资产详情二级页 */
export function DramaAssetDetailPage() {
  const { assetId } = useParams<{ assetId: string }>();
  const location = useLocation();
  const returnTo = safeNextPath((location.state as { from?: string } | null)?.from, "/drama-assets");
  const { data: detail, loading, error, run } = useAdminRequest<AdminDramaAsset>();
  const id = Number(assetId);

  const load = useCallback(() => run(() => {
    if (!Number.isSafeInteger(id) || id <= 0) return Promise.reject(new Error("无效的详情编号"));
    return api<AdminDramaAsset>(`/api/admin/drama-assets/${id}`);
  }), [id, run]);
  useEffect(() => { void load(); }, [load]);

  if (loading) {
    return <div className="admin-detail-page-loading">加载中…</div>;
  }
  if (error || !detail) return <div className="admin-route-state" role="alert"><p>{error || "未找到详情"}</p><Button onClick={() => void load()}>重新加载</Button><Button variant="outline" asChild><Link to={returnTo}>返回列表</Link></Button></div>;

  const mediaUrl = detail.cover || detail.url;

  return (
    <div className="admin-detail-page">
      <div className="admin-detail-page-toolbar">
        <Button variant="ghost" size="sm" className="admin-detail-back" asChild>
          <Link to={returnTo}>
            <ArrowLeft className="h-4 w-4" />
            返回资产库
          </Link>
        </Button>
        <div className="admin-detail-page-heading">
          <h2 className="admin-detail-page-title">
            资产 #{detail.id} · {detail.name || "未命名"}
          </h2>
          <p className="admin-detail-page-sub">
            {dramaAssetTypeLabel(detail.type)} ·{" "}
            <AdminEntityLink kind="drama" id={detail.project_id} label={detail.project_title ?? undefined} />
          </p>
        </div>
        <div className="admin-detail-page-actions">
          <Button size="sm" variant="outline" asChild>
            <Link to={`/drama-projects/${detail.project_id}`}>打开项目</Link>
          </Button>
        </div>
      </div>

      {mediaUrl ? (
        <AdminDetailSection title="媒体预览">
          <div className="admin-detail-media">
            {detail.asset_type === "video" ? (
              <video src={mediaUrl} controls className="max-w-full" />
            ) : (
              <img src={mediaUrl} alt={detail.name ?? ""} />
            )}
          </div>
        </AdminDetailSection>
      ) : null}

      <AdminDetailSection title="基本信息">
        <AdminDetailMeta
          items={[
            { label: "类型", value: dramaAssetTypeLabel(detail.type) },
            { label: "媒体类型", value: detail.asset_type },
            { label: "derive_id", value: detail.derive_id || "—" },
            {
              label: "用户",
              value: detail.user_id ? (
                <AdminEntityLink kind="user" id={detail.user_id} label={detail.user_email ?? undefined} />
              ) : (
                "—"
              ),
            },
            {
              label: "所属项目",
              value: <AdminEntityLink kind="drama" id={detail.project_id} label={detail.project_title ?? undefined} />,
            },
            { label: "生成状态", value: formatDramaGenerationStatus(detail.generation_status) },
            {
              label: "创建时间",
              value: detail.created_at ? new Date(detail.created_at).toLocaleString() : "—",
            },
            {
              label: "更新时间",
              value: detail.updated_at ? new Date(detail.updated_at).toLocaleString() : "—",
            },
          ]}
        />
      </AdminDetailSection>

      {detail.params ? (
        <AdminDetailSection title="参数 JSON">
          <pre className="admin-json-preview">{JSON.stringify(detail.params, null, 2)}</pre>
        </AdminDetailSection>
      ) : null}
    </div>
  );
}
