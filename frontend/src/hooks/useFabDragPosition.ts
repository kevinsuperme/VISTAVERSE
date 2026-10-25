/** 右下角浮钮可拖动定位，位置写入 localStorage；拖动超过阈值后吞掉 click */
import { useCallback, useEffect, useRef, useState, type CSSProperties, type PointerEvent as ReactPointerEvent } from 'react'

export type FabCornerPos = { right: number; bottom: number }

const MOVE_THRESHOLD_PX = 6

// 从 localStorage 读取浮钮位置
function readStoredPos(key: string): FabCornerPos | null {
  try {
    const raw = localStorage.getItem(key)
    if (!raw) return null
    const parsed = JSON.parse(raw) as Partial<FabCornerPos>
    const right = Number(parsed.right)
    const bottom = Number(parsed.bottom)
    if (!Number.isFinite(right) || !Number.isFinite(bottom)) return null
    return { right, bottom }
  } catch {
    return null
  }
}

// 写入 localStorage
function writeStoredPos(key: string, pos: FabCornerPos): void {
  try {
    localStorage.setItem(key, JSON.stringify(pos))
  } catch {
    /* ignore quota */
  }
}

// 把 right/bottom 夹在视口内，避免拖出屏幕
function clampFabPos(pos: FabCornerPos, btnSize = 56): FabCornerPos {
  const maxRight = Math.max(8, window.innerWidth - btnSize - 8)
  const maxBottom = Math.max(8, window.innerHeight - btnSize - 8)
  return {
    right: Math.min(maxRight, Math.max(8, pos.right)),
    bottom: Math.min(maxBottom, Math.max(8, pos.bottom)),
  }
}

/**
 * 固定右下角浮钮拖动：返回 style 与绑定到按钮的 pointer 事件。
 * 拖动后 suppressClickUntil 用于忽略紧随其后的 click。
 */
export function useFabDragPosition(
  storageKey: string,
  defaults: FabCornerPos,
  btnSize = 56,
): {
  style: CSSProperties
  bindDrag: {
    onPointerDown: (e: ReactPointerEvent<HTMLElement>) => void
    onPointerMove: (e: ReactPointerEvent<HTMLElement>) => void
    onPointerUp: (e: ReactPointerEvent<HTMLElement>) => void
    onPointerCancel: (e: ReactPointerEvent<HTMLElement>) => void
  }
  /** 若刚拖过，返回 true 并清除标记（调用方应跳过 toggle） */
  consumeDragSuppressClick: () => boolean
} {
  const [pos, setPos] = useState<FabCornerPos>(() => {
    if (typeof window === 'undefined') return defaults
    return clampFabPos(readStoredPos(storageKey) ?? defaults, btnSize)
  })
  const posRef = useRef(pos)
  const dragRef = useRef<{
    active: boolean
    moved: boolean
    startX: number
    startY: number
    originRight: number
    originBottom: number
  } | null>(null)
  const suppressClickRef = useRef(false)

  useEffect(() => {
    posRef.current = pos
  }, [pos])

  // 窗口变化时把钮夹回视口
  useEffect(() => {
    function onResize() {
      setPos((prev) => clampFabPos(prev, btnSize))
    }
    window.addEventListener('resize', onResize)
    return () => window.removeEventListener('resize', onResize)
  }, [btnSize])

  const onPointerDown = useCallback((e: ReactPointerEvent<HTMLElement>) => {
    if (e.button !== 0) return
    const cur = posRef.current
    dragRef.current = {
      active: true,
      moved: false,
      startX: e.clientX,
      startY: e.clientY,
      originRight: cur.right,
      originBottom: cur.bottom,
    }
    e.currentTarget.setPointerCapture(e.pointerId)
  }, [])

  const onPointerMove = useCallback(
    (e: ReactPointerEvent<HTMLElement>) => {
      const drag = dragRef.current
      if (!drag?.active) return
      const dx = e.clientX - drag.startX
      const dy = e.clientY - drag.startY
      if (!drag.moved && Math.abs(dx) + Math.abs(dy) < MOVE_THRESHOLD_PX) return
      drag.moved = true
      const next = clampFabPos(
        {
          right: drag.originRight - dx,
          bottom: drag.originBottom - dy,
        },
        btnSize,
      )
      setPos(next)
      posRef.current = next
    },
    [btnSize],
  )

  const endDrag = useCallback(
    (e: ReactPointerEvent<HTMLElement>) => {
      const drag = dragRef.current
      if (!drag?.active) return
      drag.active = false
      try {
        e.currentTarget.releasePointerCapture(e.pointerId)
      } catch {
        /* already released */
      }
      if (drag.moved) {
        suppressClickRef.current = true
        writeStoredPos(storageKey, posRef.current)
      }
      dragRef.current = null
    },
    [storageKey],
  )

  const consumeDragSuppressClick = useCallback(() => {
    if (!suppressClickRef.current) return false
    suppressClickRef.current = false
    return true
  }, [])

  return {
    style: {
      right: pos.right,
      bottom: pos.bottom,
      left: 'auto',
      top: 'auto',
    },
    bindDrag: {
      onPointerDown,
      onPointerMove,
      onPointerUp: endDrag,
      onPointerCancel: endDrag,
    },
    consumeDragSuppressClick,
  }
}
