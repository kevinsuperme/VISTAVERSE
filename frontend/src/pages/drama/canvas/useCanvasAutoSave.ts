/** 画布布局脏标记 → 防抖自动保存 */
import { useCallback, useEffect, useRef } from 'react'
import type { Edge, Node } from '@xyflow/react'
import { dramaApi } from '../../../api/drama'
import { CANVAS_AUTO_SAVE_MS, type CanvasAssetNodeData } from './canvasTypes'

export type CanvasSaveStatus = 'idle' | 'dirty' | 'saving' | 'saved' | 'error'

type UseCanvasAutoSaveArgs = {
  projectId: number
  nodes: Node<CanvasAssetNodeData>[]
  edges: Edge[]
  dirty: boolean
  enabled: boolean
  onSaved: () => void
  onError: (message: string) => void
  onStatus?: (status: CanvasSaveStatus) => void
}

type CanvasSnapshot = {
  projectId: number
  nodes: Node<CanvasAssetNodeData>[]
  edges: Edge[]
}
type CanvasSaveOverride = Omit<CanvasSnapshot, 'projectId'> & { projectId?: number }

/** 脏数据防抖保存到 drama canvas API；保存中再改会继续刷到最新快照 */
export function useCanvasAutoSave({
  projectId,
  nodes,
  edges,
  dirty,
  enabled,
  onSaved,
  onError,
  onStatus,
}: UseCanvasAutoSaveArgs) {
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const savingRef = useRef(false)
  const queuedRef = useRef(false)
  const dirtyEpochRef = useRef(0)
  const latestRef = useRef<CanvasSnapshot>({ nodes, edges, projectId })
  const pendingSnapshotsRef = useRef(new Map<number, CanvasSnapshot>())
  const dirtyRef = useRef(dirty)
  const flushRef = useRef<
    ((override?: CanvasSaveOverride) => Promise<void>) | null
  >(null)
  latestRef.current = { nodes, edges, projectId }
  dirtyRef.current = dirty
  if (dirty) pendingSnapshotsRef.current.set(projectId, latestRef.current)
  else pendingSnapshotsRef.current.delete(projectId)

  /** 立刻保存；可传入覆盖节点/边（删除后未等一轮渲染时用） */
  const flush = useCallback(
    async (override?: CanvasSaveOverride) => {
      if (savingRef.current) {
        queuedRef.current = true
        return
      }
      savingRef.current = true
      onStatus?.('saving')
      let oneShot = override
      let activeSaveProjectId: number | null = null
      try {
        while (true) {
          queuedRef.current = false
          const epoch = dirtyEpochRef.current
          const base = latestRef.current
          const saveProjectId = oneShot?.projectId ?? base.projectId
          activeSaveProjectId = saveProjectId
          const payloadNodes = oneShot?.nodes ?? base.nodes
          const payloadEdges = oneShot?.edges ?? base.edges
          oneShot = undefined
          await dramaApi.saveCanvas({
            project_id: saveProjectId,
            nodes: payloadNodes.map((n) => ({
              id: n.id,
              type: n.type,
              position: n.position,
              data: n.data,
            })),
            edges: payloadEdges.map((e) => ({
              id: e.id,
              source: e.source,
              target: e.target,
            })),
          })
          if (queuedRef.current || dirtyEpochRef.current !== epoch) {
            continue
          }
          // A route may have changed while the request was in flight. Avoid
          // applying the old project's callbacks to the newly loaded project.
          if (latestRef.current.projectId === saveProjectId) {
            dirtyRef.current = false
            pendingSnapshotsRef.current.delete(saveProjectId)
            onSaved()
            onStatus?.('saved')
          }
          return
        }
      } catch (err) {
        if (activeSaveProjectId === latestRef.current.projectId) {
          onStatus?.('error')
          onError(err instanceof Error ? err.message : '自动保存失败')
        }
        // 网络闪断时保持 dirty，便于稍后自动重试 / Ctrl+S
        throw err
      } finally {
        savingRef.current = false
        if (queuedRef.current) {
          queuedRef.current = false
          void flush()
        }
      }
    },
    [onError, onSaved, onStatus],
  )
  flushRef.current = flush

  useEffect(() => {
    if (!enabled || !dirty) return

    dirtyEpochRef.current += 1
    onStatus?.('dirty')

    if (timerRef.current) clearTimeout(timerRef.current)
    timerRef.current = setTimeout(() => {
      void flush()
    }, CANVAS_AUTO_SAVE_MS)

    return () => {
      if (timerRef.current) clearTimeout(timerRef.current)
    }
  }, [dirty, enabled, nodes, edges, flush, onStatus])

  // Route changes/unmounts must persist the latest snapshot. Keep this
  // separate from the debounce effect so each render does not trigger a
  // duplicate flush while React replaces effect dependencies.
  useEffect(() => {
    const flushAtUnmount = flushRef.current
    const pendingSnapshots = pendingSnapshotsRef.current
    return () => {
      if (timerRef.current) {
        clearTimeout(timerRef.current)
        timerRef.current = null
      }
      const snapshot = pendingSnapshots.get(projectId)
      if (snapshot && flushAtUnmount) void flushAtUnmount(snapshot)
    }
  }, [projectId])

  return { flush }
}
