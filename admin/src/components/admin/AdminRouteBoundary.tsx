import { Component, type ReactNode } from "react";
import { Button } from "@/components/ui/button";

export class AdminRouteBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  render() {
    if (this.state.failed) return <div className="admin-route-state" role="alert">
      <h2>页面暂时无法显示</h2><p>页面文件可能已更新，或遇到运行错误。重新加载后可继续操作。</p>
      <Button onClick={() => window.location.reload()}>重新加载页面</Button>
    </div>;
    return this.props.children;
  }
}
