import { useCallback, useEffect } from "react";
import { ArrowLeft } from "lucide-react";
import { Link, useLocation, useParams } from "react-router-dom";
import { useAdminRequest } from "@/hooks/useAdminRequest";
import { safeNextPath } from "@/lib/authRedirect";
import { api, type AdminDramaFragment } from "@/api/client";
import {
  AdminDetailMeta,
  AdminDetailSection,
} from "@/components/admin/AdminDetailLayout";
import { AdminEntityLink } from "@/components/admin/AdminEntityLink";
import { Button } from "@/components/ui/button";
import { formatDramaGenerationStatus } from "@/lib/dramaLabels";

/** 漫剧分镜详情 */
export function DramaFragmentDetailPage() {
  const { fragmentId } = useParams<{ fragmentId: string }>();
  const location = useLocation();
  const returnTo = safeNextPath((location.state as { from?: string } | null)?.from, "/drama-fragments");
  const { data: detail, loading, error, run } = useAdminRequest<AdminDramaFragment>();
  const id = Number(fragmentId);

  const load = useCallback(() => run(() => {
    if (!Number.isSafeInteger(id) || id <= 0) return Promise.reject(new Error("无效的详情编号"));
    return api<AdminDramaFragment>(`/api/admin/drama-fragments/${id}`);
  }), [id, run]);
  useEffect(() => { void load(); }, [load]);

  if (loading) {
    return <div className="admin-detail-page-loading">加载中…</div>;
  }
  if (error || !detail) return <div className="admin-route-state" role="alert"><p>{error || "未找到详情"}</p><Button onClick={() => void load()}>重新加载</Button><Button variant="outline" asChild><Link to={returnTo}>返回列表</Link></Button></div>;

  return (
    <div className="admin-detail-page">
      <div className="admin-detail-page-toolbar">
        <Button variant="ghost" size="sm" className="admin-detail-back" asChild>
          <Link to={returnTo}>
            <ArrowLeft className="h-4 w-4" />
            返回分镜列表
          </Link>
        </Button>
        <div className="admin-detail-page-heading">
          <h2 className="admin-detail-page-title">分镜 #{detail.id}</h2>
          <p className="admin-detail-page-sub">
            分集 {detail.episode_name ?? detail.episode_id} ·{" "}
            <AdminEntityLink kind="drama" id={detail.project_id} label={detail.project_title ?? undefined} />
          </p>
        </div>
        <div className="admin-detail-page-actions">
          <Button size="sm" variant="outline" asChild>
            <Link to={`/drama-episodes/${detail.episode_id}`}>打开分集</Link>
          </Button>
        </div>
      </div>

      {(detail.cover || detail.video) ? (
        <AdminDetailSection title="媒体预览">
          <div className="admin-detail-media">
            {detail.video ? (
              <video src={detail.video} controls className="max-w-full" />
            ) : detail.cover ? (
              <img src={detail.cover} alt="" />
            ) : null}
          </div>
        </AdminDetailSection>
      ) : null}

      <AdminDetailSection title="基本信息">
        <AdminDetailMeta
          items={[
            { label: "序号", value: detail.sort_order },
            {
              label: "分集",
              value: (
                <Link to={`/drama-episodes/${detail.episode_id}`} className="admin-link">
                  {detail.episode_name ?? `分集#${detail.episode_id}`}
                </Link>
              ),
            },
            {
              label: "项目",
              value: <AdminEntityLink kind="drama" id={detail.project_id} label={detail.project_title ?? undefined} />,
            },
            { label: "时长", value: detail.duration_sec != null ? `${detail.duration_sec}s` : "—" },
            { label: "生成状态", value: formatDramaGenerationStatus(detail.generation_status) },
            { label: "资产引用数", value: detail.asset_ref_count },
            { label: "剧本文本", value: detail.content || "—", full: true },
          ]}
        />
      </AdminDetailSection>

      {(detail.asset_ids ?? []).length > 0 ? (
        <AdminDetailSection title="关联资产">
          <div className="flex flex-wrap gap-2">
            {(detail.asset_ids ?? []).map((assetId) => (
              <Button key={assetId} size="sm" variant="outline" asChild>
                <Link to={`/drama-assets/${assetId}`}>资产 #{assetId}</Link>
              </Button>
            ))}
          </div>
        </AdminDetailSection>
      ) : null}

      {detail.params ? (
        <AdminDetailSection title="参数 JSON">
          <pre className="admin-json-preview">{JSON.stringify(detail.params, null, 2)}</pre>
        </AdminDetailSection>
      ) : null}
    </div>
  );
}
