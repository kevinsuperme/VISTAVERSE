import { useCallback, useEffect, useId, useRef, useState } from "react";
import { api, type AdminUserRow, type PageMeta } from "@/api/client";
import { formatAccountId, parseAccountIdQuery } from "@/lib/admin-account";
import { cn } from "@/lib/utils";

type ListRes = { items: AdminUserRow[]; meta: PageMeta };

type AdminUserSearchSelectProps = {
  value: number | null;
  onChange: (userId: number | null, user?: AdminUserRow | null) => void;
  placeholder?: string;
  className?: string;
};

/** 远程搜索用户（账号 ID + 邮箱） */
export function AdminUserSearchSelect({
  value,
  onChange,
  placeholder = "搜索用户邮箱 / 账号 ID",
  className,
}: AdminUserSearchSelectProps) {
  const [query, setQuery] = useState("");
  const [options, setOptions] = useState<AdminUserRow[]>([]);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [selectedLabel, setSelectedLabel] = useState("");
  const [activeIndex, setActiveIndex] = useState(-1);
  const inputRef = useRef<HTMLInputElement>(null);
  const listboxId = useId();
  const searchVersionRef = useRef(0);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const dropdownOpen = open && Boolean(query.trim() || options.length > 0);

  useEffect(() => () => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    searchVersionRef.current += 1;
  }, []);

  useEffect(() => {
    if (dropdownOpen && activeIndex >= 0) {
      document.getElementById(`${listboxId}-${activeIndex}`)?.scrollIntoView({ block: "nearest" });
    }
  }, [activeIndex, dropdownOpen, listboxId]);

  const loadSelected = useCallback(async (userId: number) => {
    try {
      const res = await api<ListRes>(
        `/api/admin/users?page=1&page_size=1&q=${encodeURIComponent(String(userId))}`,
      );
      const hit = res.items.find((u) => u.id === userId) ?? res.items[0];
      if (hit) {
        setSelectedLabel(`${hit.email} · ID：${formatAccountId(hit.id)}`);
      }
    } catch {
      setSelectedLabel(`ID：${formatAccountId(userId)}`);
    }
  }, []);

  useEffect(() => {
    if (value) void loadSelected(value);
    else setSelectedLabel("");
  }, [value, loadSelected]);

  const search = useCallback((raw: string) => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    const version = ++searchVersionRef.current;
    setOptions([]);
    setActiveIndex(-1);
    setLoading(Boolean(raw.trim()));
    debounceRef.current = setTimeout(async () => {
      const q = raw.trim();
      if (!q) {
        return;
      }
      try {
        const accountId = parseAccountIdQuery(q);
        const searchQ = accountId != null ? String(accountId) : q;
        const res = await api<ListRes>(
          `/api/admin/users?page=1&page_size=10&q=${encodeURIComponent(searchQ)}`,
        );
        if (version === searchVersionRef.current) setOptions(res.items);
      } catch {
        if (version === searchVersionRef.current) setOptions([]);
      } finally {
        if (version === searchVersionRef.current) setLoading(false);
      }
    }, 280);
  }, []);

  const selectUser = (user: AdminUserRow) => {
    onChange(user.id, user);
    setSelectedLabel(`${user.email} · ID：${formatAccountId(user.id)}`);
    setQuery("");
    setActiveIndex(-1);
    setOpen(false);
    inputRef.current?.focus();
  };

  return (
    <div
      className={cn("admin-user-search", className)}
      onBlur={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget)) setOpen(false);
      }}
    >
      <input
        ref={inputRef}
        type="search"
        role="combobox"
        aria-label={placeholder}
        aria-autocomplete="list"
        aria-haspopup="listbox"
        aria-expanded={dropdownOpen}
        aria-controls={dropdownOpen ? listboxId : undefined}
        aria-activedescendant={dropdownOpen && activeIndex >= 0 ? `${listboxId}-${activeIndex}` : undefined}
        autoComplete="off"
        className="admin-input"
        placeholder={value ? selectedLabel || placeholder : placeholder}
        value={open ? query : value ? selectedLabel : query}
        onChange={(e) => {
          setQuery(e.target.value);
          setOpen(true);
          search(e.target.value);
        }}
        onFocus={() => setOpen(true)}
        onKeyDown={(event) => {
          if (event.nativeEvent.isComposing) return;
          if (event.key === "ArrowDown" || event.key === "ArrowUp") {
            event.preventDefault();
            setOpen(true);
            if (options.length) {
              const direction = event.key === "ArrowDown" ? 1 : -1;
              setActiveIndex((index) => index < 0
                ? direction > 0 ? 0 : options.length - 1
                : (index + direction + options.length) % options.length);
            }
          } else if (event.key === "Enter" && dropdownOpen && activeIndex >= 0) {
            event.preventDefault();
            selectUser(options[activeIndex]);
          } else if (event.key === "Escape" && dropdownOpen) {
            event.preventDefault();
            event.stopPropagation();
            setOpen(false);
            setActiveIndex(-1);
          } else if (event.key === "Tab") {
            setOpen(false);
            setActiveIndex(-1);
          }
        }}
      />
      {value ? (
        <button
          type="button"
          className="admin-user-search-clear"
          onClick={() => {
            onChange(null, null);
            setQuery("");
            setSelectedLabel("");
            setOptions([]);
            setActiveIndex(-1);
            searchVersionRef.current += 1;
            if (debounceRef.current) clearTimeout(debounceRef.current);
            setLoading(false);
            inputRef.current?.focus();
          }}
          aria-label="清除用户"
        >
          ×
        </button>
      ) : null}
      {dropdownOpen ? (
        <div className="admin-user-search-dropdown">
          {loading ? <div className="admin-user-search-empty" role="status">搜索中…</div> : null}
          {!loading && options.length === 0 ? (
            <div className="admin-user-search-empty" role="status">无匹配用户</div>
          ) : null}
          <div id={listboxId} role="listbox" aria-label="用户搜索结果" aria-busy={loading}>
            {options.map((u, index) => (
              <button
                key={u.id}
                id={`${listboxId}-${index}`}
                type="button"
                role="option"
                tabIndex={-1}
                aria-selected={u.id === value}
                data-active={index === activeIndex || undefined}
                className="admin-user-search-option"
                onMouseDown={(e) => e.preventDefault()}
                onMouseMove={() => setActiveIndex(index)}
                onClick={() => selectUser(u)}
              >
                <span className="font-medium">{u.email}</span>
                <span className="text-xs text-[var(--admin-muted)]">
                  ID：{formatAccountId(u.id)}
                  {u.nickname ? ` · ${u.nickname}` : ""}
                </span>
              </button>
            ))}
          </div>
        </div>
      ) : null}
    </div>
  );
}
