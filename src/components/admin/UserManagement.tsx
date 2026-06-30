import React, { useState, useEffect, useCallback } from 'react';
import {
  Users, Plus, X, RefreshCw, Search, ChevronDown, MoreHorizontal,
  UserCog, Ban, CheckCircle, AlertTriangle, Clock, Activity,
  Shield, Eye, EyeOff, Trash2, Loader2, UserPlus
} from 'lucide-react';
import { useAuthStore } from '../../stores/useAuthStore';

// Inner error boundary to prevent table rendering crashes from taking down the whole admin page
class TableErrorBoundary extends React.Component<{ children: React.ReactNode }, { hasError: boolean }> {
  constructor(props: { children: React.ReactNode }) {
    super(props);
    this.state = { hasError: false };
  }
  static getDerivedStateFromError() {
    return { hasError: true };
  }
  render() {
    if (this.state.hasError) {
      return (
        <div className="flex flex-col items-center justify-center py-16 text-zinc-400">
          <AlertTriangle size={28} className="text-red-400 mb-3" />
          <span className="text-sm text-red-500">用户列表渲染出错</span>
          <button
            onClick={() => this.setState({ hasError: false })}
            className="mt-3 text-xs text-indigo-500 hover:text-indigo-600 font-medium"
          >
            点击重试
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}


interface UserInfo {
  user_id: string;
  username: string;
  display_name: string;
  role: 'admin' | 'researcher' | 'viewer';
  status: 'active' | 'deactivated';
  created_at: string;
  last_login: string | null;
}

interface QueryRecord {
  job_id: string;
  symbol: string;
  market: string;
  analysis_level: string;
  status: string;
  created_at: string;
}

const ROLE_LABELS: Record<string, string> = {
  admin: '管理员',
  researcher: '研究员',
  viewer: '观察者',
};

const ROLE_COLORS: Record<string, string> = {
  admin: 'bg-red-100 text-red-700',
  researcher: 'bg-blue-100 text-blue-700',
  viewer: 'bg-zinc-100 text-zinc-600',
};

const STATUS_LABELS: Record<string, string> = {
  active: '正常',
  deactivated: '已禁用',
};

function getAuthHeaders(): HeadersInit {
  const token = localStorage.getItem('auth_token');
  return {
    'Authorization': `Bearer ${token}`,
    'Content-Type': 'application/json',
  };
}

function formatRelativeTime(dateStr: string | null): string {
  if (!dateStr) return '从未登录';
  const diff = Date.now() - new Date(dateStr).getTime();
  if (diff < 0) return '刚刚';
  if (diff < 60_000) return `${Math.floor(diff / 1000)}秒前`;
  if (diff < 3_600_000) return `${Math.floor(diff / 60_000)}分钟前`;
  if (diff < 86_400_000) return `${Math.floor(diff / 3_600_000)}小时前`;
  if (diff < 2_592_000_000) return `${Math.floor(diff / 86_400_000)}天前`;
  return `${Math.floor(diff / 2_592_000_000)}月前`;
}

function formatDate(dateStr: string | null | undefined): string {
  if (!dateStr) return '—';
  try {
    return new Date(dateStr).toLocaleString('zh-CN', {
      year: 'numeric', month: '2-digit', day: '2-digit',
      hour: '2-digit', minute: '2-digit',
      timeZone: 'Asia/Shanghai',
    });
  } catch {
    return dateStr;
  }
}

function RoleBadge({ role }: { role: string }) {
  return (
    <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full uppercase tracking-wider ${ROLE_COLORS[role] || 'bg-zinc-100 text-zinc-600'}`}>
      {ROLE_LABELS[role] || role}
    </span>
  );
}

function StatusBadge({ status }: { status: string }) {
  return (
    <span className={`inline-flex items-center gap-1 text-xs font-semibold px-2 py-0.5 rounded-full ${
      status === 'active'
        ? 'bg-emerald-100 text-emerald-700'
        : 'bg-red-100 text-red-600'
    }`}>
      <span className={`w-1.5 h-1.5 rounded-full ${status === 'active' ? 'bg-emerald-500' : 'bg-red-400'}`} />
      {STATUS_LABELS[status] || status}
    </span>
  );
}

function OnlineStatusBadge({ lastLogin }: { lastLogin: string | null }) {
  if (!lastLogin) return <span className="text-xs text-zinc-400">离线</span>;
  const diff = Date.now() - new Date(lastLogin).getTime();
  const isOnline = diff < 15 * 60 * 1000;
  return (
    <span className={`inline-flex items-center gap-1 text-xs font-semibold px-2 py-0.5 rounded-full ${
      isOnline ? 'bg-emerald-100 text-emerald-700' : 'bg-zinc-100 text-zinc-600'
    }`}>
      <span className={`w-1.5 h-1.5 rounded-full ${isOnline ? 'bg-emerald-500' : 'bg-zinc-400'}`} />
      {isOnline ? '在线' : '离线'}
    </span>
  );
}

export function UserManagement() {
  const currentUser = useAuthStore(s => s.user);
  const [users, setUsers] = useState<UserInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Add user modal
  const [showAddModal, setShowAddModal] = useState(false);
  const [addForm, setAddForm] = useState({ username: '', password: '', display_name: '', role: 'viewer' });
  const [addFormErrors, setAddFormErrors] = useState<Record<string, string>>({});
  const [addSubmitting, setAddSubmitting] = useState(false);
  const [addServerError, setAddServerError] = useState<string | null>(null);

  // Per-user action state
  const [openActionMenu, setOpenActionMenu] = useState<string | null>(null);
  const [editingRoleUser, setEditingRoleUser] = useState<string | null>(null);
  const [editingRoleValue, setEditingRoleValue] = useState<string>('');
  const [actionFeedback, setActionFeedback] = useState<{ userId: string; type: 'success' | 'error'; msg: string } | null>(null);

  // Confirm deactivate/delete modal
  const [confirmUser, setConfirmUser] = useState<UserInfo | null>(null);
  const [confirmAction, setConfirmAction] = useState<'deactivate' | 'activate' | 'delete' | null>(null);
  const [confirmSubmitting, setConfirmSubmitting] = useState(false);

  // Query history
  const [queryUser, setQueryUser] = useState<UserInfo | null>(null);
  const [queries, setQueries] = useState<QueryRecord[]>([]);
  const [queriesLoading, setQueriesLoading] = useState(false);
  const [queriesError, setQueriesError] = useState<string | null>(null);

  // Auth status
  const [unauthorized, setUnauthorized] = useState(false);

  const fetchUsers = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch('/api/auth/users', { headers: getAuthHeaders() });
      if (res.status === 401 || res.status === 403) {
        setUnauthorized(true);
        return;
      }
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || data.error || '获取用户列表失败');
      }
      const data = await res.json();
      setUsers(Array.isArray(data) ? data : data.data || data.users || []);
    } catch (e) {
      setError(e instanceof Error ? e.message : '网络错误，请稍后重试');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchUsers();
  }, [fetchUsers]);

  // Close action menu on outside click
  useEffect(() => {
    if (!openActionMenu) return;
    const handler = () => setOpenActionMenu(null);
    document.addEventListener('click', handler);
    return () => document.removeEventListener('click', handler);
  }, [openActionMenu]);

  // Clear feedback after timeout
  useEffect(() => {
    if (!actionFeedback) return;
    const t = setTimeout(() => setActionFeedback(null), 3000);
    return () => clearTimeout(t);
  }, [actionFeedback]);

  // ── Add User ──
  function validateAddForm(): boolean {
    const errors: Record<string, string> = {};
    if (!addForm.username.trim()) errors.username = '用户名不能为空';
    if (!addForm.password) errors.password = '密码不能为空';
    else if (addForm.password.length < 6) errors.password = '密码至少6个字符';
    setAddFormErrors(errors);
    return Object.keys(errors).length === 0;
  }

  async function handleAddUser() {
    if (!validateAddForm()) return;
    setAddSubmitting(true);
    setAddServerError(null);
    try {
      const body: Record<string, string> = {
        username: addForm.username.trim(),
        password: addForm.password,
        role: addForm.role,
      };
      if (addForm.display_name.trim()) body.display_name = addForm.display_name.trim();

      const res = await fetch('/api/auth/admin-create-user', {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify(body),
      });
      if (res.status === 401 || res.status === 403) {
        setUnauthorized(true);
        return;
      }
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || data.error || '创建用户失败');
      }
      setShowAddModal(false);
      setAddForm({ username: '', password: '', display_name: '', role: 'viewer' });
      setAddFormErrors({});
      setActionFeedback({ userId: '', type: 'success', msg: '用户创建成功' });
      fetchUsers();
    } catch (e) {
      setAddServerError(e instanceof Error ? e.message : '创建失败');
    } finally {
      setAddSubmitting(false);
    }
  }

  // ── Update Role ──
  async function handleUpdateRole(userId: string, role: string) {
    setEditingRoleUser(null);
    try {
      const res = await fetch(`/api/auth/users/${userId}`, {
        method: 'PUT',
        headers: getAuthHeaders(),
        body: JSON.stringify({ role }),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || data.error || '更新角色失败');
      }
      setActionFeedback({ userId, type: 'success', msg: `角色已更新为 ${ROLE_LABELS[role] || role}` });
      fetchUsers();
    } catch (e) {
      setActionFeedback({ userId, type: 'error', msg: e instanceof Error ? e.message : '更新失败' });
    }
  }

  // ── Toggle Status ──
  async function handleToggleStatus(user: UserInfo) {
    const isDeactivate = user.status === 'active';
    setConfirmUser(user);
    setConfirmAction(isDeactivate ? 'deactivate' : 'activate');
  }

  async function executeToggleStatus() {
    if (!confirmUser || !confirmAction) return;
    const user = confirmUser;
    setConfirmUser(null);
    setConfirmAction(null);

    try {
      const res = await fetch(`/api/auth/users/${user.user_id}`, {
        method: 'PUT',
        headers: getAuthHeaders(),
        body: JSON.stringify({ status: confirmAction === 'deactivate' ? 'deactivated' : 'active' }),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || data.error || '操作失败');
      }
      setActionFeedback({
        userId: user.user_id,
        type: 'success',
        msg: confirmAction === 'deactivate' ? '用户已禁用' : '用户已启用',
      });
      fetchUsers();
    } catch (e) {
      setActionFeedback({
        userId: user.user_id,
        type: 'error',
        msg: e instanceof Error ? e.message : '操作失败',
      });
    }
  }

  // ── Delete User ──
  function handleDeleteUser(user: UserInfo) {
    setConfirmUser(user);
    setConfirmAction('delete');
  }

  async function executeDeleteUser() {
    if (!confirmUser) return;
    const user = confirmUser;
    setConfirmSubmitting(true);
    try {
      const res = await fetch(`/api/auth/users/${user.user_id}`, {
        method: 'DELETE',
        headers: getAuthHeaders(),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || data.error || '删除用户失败');
      }
      setConfirmUser(null);
      setConfirmAction(null);
      setActionFeedback({ userId: user.user_id, type: 'success', msg: '用户及所有关联数据已永久删除' });
      fetchUsers();
    } catch (e) {
      setActionFeedback({
        userId: user.user_id,
        type: 'error',
        msg: e instanceof Error ? e.message : '删除失败',
      });
      setConfirmUser(null);
      setConfirmAction(null);
    } finally {
      setConfirmSubmitting(false);
    }
  }

  // ── Fetch Queries ──
  async function handleViewQueries(user: UserInfo) {
    setQueryUser(user);
    setQueries([]);
    setQueriesLoading(true);
    setQueriesError(null);
    try {
      const res = await fetch(`/api/auth/users/${user.user_id}/queries`, { headers: getAuthHeaders() });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || data.error || '获取查询记录失败');
      }
      const data = await res.json();
      setQueries(data.queries || []);
    } catch (e) {
      setQueriesError(e instanceof Error ? e.message : '获取记录失败');
    } finally {
      setQueriesLoading(false);
    }
  }

  // ── Action Menu ──
  function ActionMenu({ user }: { user: UserInfo }) {
    const isOpen = openActionMenu === user.user_id;

    return (
      <div className="relative">
        <button
          onClick={(e) => { e.stopPropagation(); setOpenActionMenu(isOpen ? null : user.user_id); }}
          className="p-1.5 rounded-lg text-zinc-400 hover:text-zinc-700 hover:bg-zinc-100 transition-colors"
        >
          <MoreHorizontal size={16} />
        </button>
        {isOpen && (
          <div className="absolute right-0 top-full mt-1 w-44 bg-white rounded-xl border border-zinc-200 shadow-lg z-50 py-1 text-xs">
            <button
              onClick={() => { setOpenActionMenu(null); handleViewQueries(user); }}
              className="w-full flex items-center gap-2 px-3 py-2 text-zinc-700 hover:bg-zinc-50 transition-colors"
            >
              <Search size={13} className="text-blue-500" />
              查看查询记录
            </button>
            <button
              onClick={() => {
                setOpenActionMenu(null);
                setEditingRoleUser(user.user_id);
                setEditingRoleValue(user.role);
              }}
              className="w-full flex items-center gap-2 px-3 py-2 text-zinc-700 hover:bg-zinc-50 transition-colors"
            >
              <UserCog size={13} className="text-violet-500" />
              编辑角色
            </button>
            <button
              onClick={() => { setOpenActionMenu(null); handleToggleStatus(user); }}
              className="w-full flex items-center gap-2 px-3 py-2 text-zinc-700 hover:bg-zinc-50 transition-colors"
            >
              {user.status === 'active' ? (
                <><Ban size={13} className="text-amber-500" /> 禁用用户</>
              ) : (
                <><CheckCircle size={13} className="text-emerald-500" /> 启用用户</>
              )}
            </button>
            <hr className="my-1 border-zinc-100" />
            <button
              onClick={() => { setOpenActionMenu(null); handleDeleteUser(user); }}
              className="w-full flex items-center gap-2 px-3 py-2 text-red-600 hover:bg-red-50 transition-colors"
            >
              <Trash2 size={13} />
              删除用户
            </button>
          </div>
        )}
      </div>
    );
  }

  // ── Role Edit Inline ──
  function RoleEditor({ user }: { user: UserInfo }) {
    if (editingRoleUser !== user.user_id) {
      return <RoleBadge role={user.role} />;
    }

    return (
      <div className="flex items-center gap-1.5">
        <select
          value={editingRoleValue}
          onChange={(e) => setEditingRoleValue(e.target.value)}
          className="text-xs px-2 py-1 rounded-lg border border-zinc-200 bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500"
          autoFocus
        >
          <option value="admin">管理员</option>
          <option value="researcher">研究员</option>
          <option value="viewer">观察者</option>
        </select>
        <button
          onClick={() => handleUpdateRole(user.user_id, editingRoleValue)}
          className="p-1 rounded text-emerald-600 hover:bg-emerald-50 transition-colors"
          title="确认"
        >
          <CheckCircle size={14} />
        </button>
        <button
          onClick={() => setEditingRoleUser(null)}
          className="p-1 rounded text-zinc-400 hover:bg-zinc-100 transition-colors"
          title="取消"
        >
          <X size={14} />
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* ── Header ── */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="flex items-center gap-2 text-xl font-semibold text-zinc-900">
            <Users size={20} className="text-indigo-500" />
            用户管理
          </h2>
          <div className="flex items-center gap-2 mt-0.5">
            <p className="text-xs text-zinc-400">管理系统用户、角色和权限</p>
            {currentUser && (
              <span className="inline-flex items-center gap-1.5 text-[11px] font-medium text-indigo-700 bg-indigo-50 border border-indigo-100 px-2.5 py-0.5 rounded-full">
                <span className="relative flex h-2 w-2">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-indigo-400 opacity-75"></span>
                  <span className="relative inline-flex rounded-full h-2 w-2 bg-indigo-500"></span>
                </span>
                当前登录: {currentUser.display_name || currentUser.username}
              </span>
            )}
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={fetchUsers}
            className="flex items-center gap-1.5 text-xs font-medium text-zinc-500 hover:text-zinc-700 px-3 py-1.5 rounded-xl border border-zinc-200 hover:bg-zinc-50 transition-all"
          >
            <RefreshCw size={12} className={loading ? 'animate-spin' : ''} />
            刷新
          </button>
          <button
            onClick={() => {
              setAddForm({ username: '', password: '', display_name: '', role: 'viewer' });
              setAddFormErrors({});
              setAddServerError(null);
              setShowAddModal(true);
            }}
            className="flex items-center gap-1.5 text-xs font-medium text-white bg-indigo-500 hover:bg-indigo-600 px-3 py-1.5 rounded-xl shadow-sm shadow-indigo-200 transition-all"
          >
            <UserPlus size={13} />
            新增用户
          </button>
        </div>
      </div>

      {/* ── Action Feedback Toast ── */}
      {actionFeedback && (
        <div className={`flex items-center gap-2 px-4 py-2.5 rounded-xl text-xs font-medium shadow-sm border ${
          actionFeedback.type === 'success'
            ? 'bg-emerald-50 border-emerald-200 text-emerald-700'
            : 'bg-red-50 border-red-200 text-red-600'
        }`}>
          {actionFeedback.type === 'success'
            ? <CheckCircle size={14} className="flex-shrink-0" />
            : <AlertTriangle size={14} className="flex-shrink-0" />
          }
          {actionFeedback.msg}
        </div>
      )}

      {/* ── User Table ── */}
      <div className="bg-white rounded-2xl border border-zinc-100 shadow-sm overflow-hidden">
        {unauthorized ? (
          <div className="flex flex-col items-center justify-center py-16 text-zinc-400">
            <Ban size={32} className="mb-3 text-amber-400" />
            <span className="text-sm font-medium text-zinc-600">无权限访问</span>
            <p className="text-xs text-zinc-400 mt-1">您需要管理员权限才能查看用户管理</p>
            <button
              onClick={() => { window.location.hash = '#/admin'; }}
              className="mt-4 px-4 py-2 text-xs font-medium text-indigo-600 bg-indigo-50 rounded-xl hover:bg-indigo-100 transition-colors"
            >
              返回系统监控
            </button>
          </div>
        ) : loading ? (
          <div className="flex flex-col items-center justify-center py-16 text-zinc-400">
            <Loader2 size={28} className="animate-spin text-indigo-500 mb-3" />
            <span className="text-sm">加载用户列表...</span>
          </div>
        ) : error ? (
          <div className="flex flex-col items-center justify-center py-16 text-zinc-400">
            <AlertTriangle size={28} className="text-red-400 mb-3" />
            <span className="text-sm text-red-500">{error}</span>
            <button
              onClick={fetchUsers}
              className="mt-3 text-xs text-indigo-500 hover:text-indigo-600 font-medium"
            >
              点击重试
            </button>
          </div>
        ) : users.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 text-zinc-400">
            <Users size={32} className="mb-3 text-zinc-300" />
            <span className="text-sm">暂无用户</span>
            <button
              onClick={() => {
                setAddForm({ username: '', password: '', display_name: '', role: 'viewer' });
                setAddFormErrors({});
                setAddServerError(null);
                setShowAddModal(true);
              }}
              className="mt-3 text-xs text-indigo-500 hover:text-indigo-600 font-medium"
            >
              新增第一个用户
            </button>
          </div>
        ) : (
          <TableErrorBoundary>
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-zinc-100 bg-zinc-50/50">
                  <th className="text-left font-semibold text-zinc-500 px-4 py-3">用户名</th>
                  <th className="text-left font-semibold text-zinc-500 px-4 py-3">显示名称</th>
                  <th className="text-left font-semibold text-zinc-500 px-4 py-3">角色</th>
                  <th className="text-left font-semibold text-zinc-500 px-4 py-3">账号状态</th>
                  <th className="text-left font-semibold text-zinc-500 px-4 py-3">登录状态</th>
                  <th className="text-left font-semibold text-zinc-500 px-4 py-3">创建时间</th>
                  <th className="text-left font-semibold text-zinc-500 px-4 py-3">最后登录</th>
                  <th className="text-right font-semibold text-zinc-500 px-4 py-3">操作</th>
                </tr>
              </thead>
              <tbody>
                {users.map((user) => (
                  <tr key={user.user_id} className="border-b border-zinc-50 hover:bg-zinc-50/50 transition-colors">
                    <td className="px-4 py-3">
                      <span className="font-medium text-zinc-800 flex items-center gap-2">
                        {user.username}
                        {currentUser?.username === user.username && (
                          <span className="text-[10px] font-bold px-1.5 py-0.5 rounded bg-indigo-100 text-indigo-700">我</span>
                        )}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-zinc-500">
                      {user.display_name || '—'}
                    </td>
                    <td className="px-4 py-3">
                      <RoleEditor user={user} />
                    </td>
                    <td className="px-4 py-3">
                      <StatusBadge status={user.status} />
                    </td>
                    <td className="px-4 py-3">
                      <OnlineStatusBadge lastLogin={user.last_login} />
                    </td>
                    <td className="px-4 py-3 text-zinc-500 whitespace-nowrap">
                      {formatDate(user.created_at)}
                    </td>
                    <td className="px-4 py-3 text-zinc-500 whitespace-nowrap">
                      <div className="flex flex-col">
                        <span>{formatRelativeTime(user.last_login)}</span>
                        {user.last_login && <span className="text-[10px] text-zinc-400">{formatDate(user.last_login)}</span>}
                      </div>
                    </td>
                    <td className="px-4 py-3 text-right">
                      <ActionMenu user={user} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          </TableErrorBoundary>
        )}
      </div>

      {/* ── Confirmation Dialog ── */}
      {confirmUser && (
        <div className="fixed inset-0 z-[200] flex items-center justify-center p-4 bg-zinc-950/40 backdrop-blur-sm">
          <div className="bg-white rounded-2xl w-full max-w-sm overflow-hidden shadow-2xl border border-zinc-100">
            <div className="px-5 py-4 border-b border-zinc-100 flex items-center gap-2 bg-zinc-50/50">
              {confirmAction === 'delete' ? (
                <Trash2 size={16} className="text-red-500" />
              ) : (
                <AlertTriangle size={16} className="text-amber-500" />
              )}
              <h3 className="font-bold text-zinc-800">
                {confirmAction === 'delete' ? '确认永久删除用户' :
                 confirmAction === 'deactivate' ? '确认禁用用户' : '确认启用用户'}
              </h3>
            </div>
            <div className="p-5">
              {confirmAction === 'delete' ? (
                <div className="space-y-3">
                  <p className="text-xs text-zinc-600 leading-relaxed">
                    确定要<strong className="text-red-600">永久删除</strong>用户 <strong className="text-zinc-800">{confirmUser.username}</strong> 吗？
                  </p>
                  <div className="bg-red-50 border border-red-200 rounded-xl px-3 py-2.5">
                    <p className="text-[11px] text-red-600 leading-relaxed">
                      此操作不可撤销！以下所有关联数据将被永久删除：
                    </p>
                    <ul className="text-[11px] text-red-500 mt-1.5 space-y-0.5 list-disc list-inside">
                      <li>用户账号信息</li>
                      <li>自选股列表及项目</li>
                      <li>分析记录与报告</li>
                      <li>模拟交易账户及持仓</li>
                      <li>交易信号与预警</li>
                      <li>交易日志与决策记录</li>
                    </ul>
                  </div>
                </div>
              ) : (
                <p className="text-xs text-zinc-600 leading-relaxed">
                  {confirmAction === 'deactivate' ? (
                    <>确定要禁用用户 <strong className="text-zinc-800">{confirmUser.username}</strong> 吗？禁用后该用户将无法登录系统，但所有数据会被保留。</>
                  ) : (
                    <>确定要启用用户 <strong className="text-zinc-800">{confirmUser.username}</strong> 吗？启用后该用户可重新登录系统。</>
                  )}
                </p>
              )}
            </div>
            <div className="px-5 py-4 border-t border-zinc-100 flex justify-end gap-2 bg-zinc-50/50">
              <button
                onClick={() => { setConfirmUser(null); setConfirmAction(null); }}
                disabled={confirmSubmitting}
                className="px-4 py-2 text-xs font-medium text-zinc-600 hover:text-zinc-800 hover:bg-zinc-200/50 rounded-xl transition-colors disabled:opacity-50"
              >
                取消
              </button>
              {confirmAction === 'delete' ? (
                <button
                  onClick={executeDeleteUser}
                  disabled={confirmSubmitting}
                  className="px-4 py-2 text-xs font-medium text-white bg-red-500 hover:bg-red-600 disabled:bg-red-300 rounded-xl shadow-sm shadow-red-200 transition-colors flex items-center gap-1.5"
                >
                  {confirmSubmitting ? <Loader2 size={14} className="animate-spin" /> : <Trash2 size={14} />}
                  {confirmSubmitting ? '删除中...' : '确认永久删除'}
                </button>
              ) : (
                <button
                  onClick={executeToggleStatus}
                  className={`px-4 py-2 text-xs font-medium text-white rounded-xl shadow-sm transition-colors flex items-center gap-1.5 ${
                    confirmAction === 'deactivate'
                      ? 'bg-red-500 hover:bg-red-600 shadow-red-200'
                      : 'bg-emerald-500 hover:bg-emerald-600 shadow-emerald-200'
                  }`}
                >
                  <CheckCircle size={14} />
                  {confirmAction === 'deactivate' ? '确认禁用' : '确认启用'}
                </button>
              )}
            </div>
          </div>
        </div>
      )}

      {/* ── Add User Modal ── */}
      {showAddModal && (
        <div className="fixed inset-0 z-[200] flex items-center justify-center p-4 bg-zinc-950/40 backdrop-blur-sm">
          <div className="bg-white rounded-2xl w-full max-w-md overflow-hidden shadow-2xl border border-zinc-100 flex flex-col">
            <div className="px-5 py-4 border-b border-zinc-100 flex items-center justify-between bg-zinc-50/50">
              <h3 className="font-bold text-zinc-800 flex items-center gap-2">
                <UserPlus size={16} className="text-indigo-500" />
                新增用户
              </h3>
              <button
                onClick={() => setShowAddModal(false)}
                className="text-zinc-400 hover:text-zinc-600 transition-colors"
              >
                <X size={16} />
              </button>
            </div>

            <div className="p-5 space-y-4">
              {/* Server error */}
              {addServerError && (
                <div className="flex items-center gap-2 px-3 py-2 rounded-xl bg-red-50 border border-red-200 text-xs text-red-600">
                  <AlertTriangle size={13} className="flex-shrink-0" />
                  {addServerError}
                </div>
              )}

              {/* Username */}
              <div>
                <label className="block text-xs font-medium text-zinc-500 mb-1.5">
                  用户名 <span className="text-red-400">*</span>
                </label>
                <input
                  type="text"
                  value={addForm.username}
                  onChange={(e) => setAddForm({ ...addForm, username: e.target.value })}
                  className={`w-full px-3 py-2 text-sm bg-zinc-50 border rounded-xl text-zinc-800 focus:outline-none focus:ring-2 focus:ring-indigo-500/20 transition-all ${
                    addFormErrors.username ? 'border-red-300' : 'border-zinc-200 focus:border-indigo-500'
                  }`}
                  placeholder="请输入用户名"
                  autoFocus
                />
                {addFormErrors.username && (
                  <p className="text-[10px] text-red-500 mt-1">{addFormErrors.username}</p>
                )}
              </div>

              {/* Password */}
              <div>
                <label className="block text-xs font-medium text-zinc-500 mb-1.5">
                  密码 <span className="text-red-400">*</span>
                </label>
                <input
                  type="password"
                  value={addForm.password}
                  onChange={(e) => setAddForm({ ...addForm, password: e.target.value })}
                  className={`w-full px-3 py-2 text-sm bg-zinc-50 border rounded-xl text-zinc-800 focus:outline-none focus:ring-2 focus:ring-indigo-500/20 transition-all ${
                    addFormErrors.password ? 'border-red-300' : 'border-zinc-200 focus:border-indigo-500'
                  }`}
                  placeholder="至少6个字符"
                />
                {addFormErrors.password && (
                  <p className="text-[10px] text-red-500 mt-1">{addFormErrors.password}</p>
                )}
              </div>

              {/* Display Name */}
              <div>
                <label className="block text-xs font-medium text-zinc-500 mb-1.5">显示名称</label>
                <input
                  type="text"
                  value={addForm.display_name}
                  onChange={(e) => setAddForm({ ...addForm, display_name: e.target.value })}
                  className="w-full px-3 py-2 text-sm bg-zinc-50 border border-zinc-200 rounded-xl text-zinc-800 focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500 transition-all"
                  placeholder="可选，默认为用户名"
                />
              </div>

              {/* Role */}
              <div>
                <label className="block text-xs font-medium text-zinc-500 mb-1.5">角色</label>
                <select
                  value={addForm.role}
                  onChange={(e) => setAddForm({ ...addForm, role: e.target.value })}
                  className="w-full px-3 py-2 text-sm bg-zinc-50 border border-zinc-200 rounded-xl text-zinc-800 focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500 transition-all"
                >
                  <option value="viewer">观察者</option>
                  <option value="researcher">研究员</option>
                  <option value="admin">管理员</option>
                </select>
              </div>
            </div>

            <div className="px-5 py-4 border-t border-zinc-100 flex justify-end gap-2 bg-zinc-50/50">
              <button
                onClick={() => setShowAddModal(false)}
                className="px-4 py-2 text-xs font-medium text-zinc-600 hover:text-zinc-800 hover:bg-zinc-200/50 rounded-xl transition-colors"
              >
                取消
              </button>
              <button
                onClick={handleAddUser}
                disabled={addSubmitting}
                className="px-4 py-2 text-xs font-medium text-white bg-indigo-500 hover:bg-indigo-600 disabled:bg-indigo-300 rounded-xl shadow-sm shadow-indigo-200 transition-colors flex items-center gap-1.5"
              >
                {addSubmitting ? <Loader2 size={13} className="animate-spin" /> : <UserPlus size={13} />}
                {addSubmitting ? '创建中...' : '创建用户'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── Query History Panel ── */}
      {queryUser && (
        <div className="fixed inset-0 z-[200] flex items-center justify-center p-4 bg-zinc-950/40 backdrop-blur-sm">
          <div className="bg-white rounded-2xl w-full max-w-2xl max-h-[80vh] overflow-hidden shadow-2xl border border-zinc-100 flex flex-col">
            <div className="px-5 py-4 border-b border-zinc-100 flex items-center justify-between bg-zinc-50/50">
              <h3 className="font-bold text-zinc-800 flex items-center gap-2">
                <Search size={16} className="text-indigo-500" />
                {queryUser.display_name || queryUser.username} 的查询记录
              </h3>
              <button
                onClick={() => { setQueryUser(null); setQueries([]); }}
                className="text-zinc-400 hover:text-zinc-600 transition-colors"
              >
                <X size={16} />
              </button>
            </div>

            <div className="flex-1 overflow-y-auto p-5">
              {queriesLoading ? (
                <div className="flex flex-col items-center justify-center py-12 text-zinc-400">
                  <Loader2 size={24} className="animate-spin text-indigo-500 mb-3" />
                  <span className="text-xs">加载查询记录...</span>
                </div>
              ) : queriesError ? (
                <div className="flex flex-col items-center justify-center py-12 text-zinc-400">
                  <AlertTriangle size={24} className="text-red-400 mb-3" />
                  <span className="text-xs text-red-500">{queriesError}</span>
                </div>
              ) : queries.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-12 text-zinc-400">
                  <Search size={28} className="text-zinc-300 mb-3" />
                  <span className="text-xs">暂无查询记录</span>
                </div>
              ) : (
                <table className="w-full text-xs">
                  <thead>
                    <tr className="border-b border-zinc-100">
                      <th className="text-left font-semibold text-zinc-500 px-3 py-2">股票</th>
                      <th className="text-left font-semibold text-zinc-500 px-3 py-2">市场</th>
                      <th className="text-left font-semibold text-zinc-500 px-3 py-2">分析深度</th>
                      <th className="text-left font-semibold text-zinc-500 px-3 py-2">状态</th>
                      <th className="text-left font-semibold text-zinc-500 px-3 py-2">时间</th>
                    </tr>
                  </thead>
                  <tbody>
                    {queries.map((q) => (
                      <tr key={q.job_id} className="border-b border-zinc-50 hover:bg-zinc-50/50 transition-colors">
                        <td className="px-3 py-2.5 font-medium text-zinc-800">{q.symbol}</td>
                        <td className="px-3 py-2.5 text-zinc-500">{q.market}</td>
                        <td className="px-3 py-2.5">
                          <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded-full ${
                            q.analysis_level === 'deep' ? 'bg-violet-100 text-violet-700' :
                            q.analysis_level === 'standard' ? 'bg-blue-100 text-blue-700' :
                            q.analysis_level === 'quick' ? 'bg-emerald-100 text-emerald-700' :
                            'bg-zinc-100 text-zinc-600'
                          }`}>
                            {q.analysis_level === 'deep' ? '深度' :
                             q.analysis_level === 'standard' ? '标准' :
                             q.analysis_level === 'quick' ? '快速' : q.analysis_level}
                          </span>
                        </td>
                        <td className="px-3 py-2.5">
                          <span className={`inline-flex items-center gap-1 text-[10px] font-semibold px-1.5 py-0.5 rounded-full ${
                            q.status === 'completed' ? 'bg-emerald-100 text-emerald-700' :
                            q.status === 'running' || q.status === 'pending' ? 'bg-amber-100 text-amber-700' :
                            q.status === 'failed' ? 'bg-red-100 text-red-600' :
                            'bg-zinc-100 text-zinc-500'
                          }`}>
                            {q.status === 'completed' ? '完成' :
                             q.status === 'running' ? '进行中' :
                             q.status === 'pending' ? '等待中' :
                             q.status === 'failed' ? '失败' : q.status}
                          </span>
                        </td>
                        <td className="px-3 py-2.5 text-zinc-500 whitespace-nowrap">
                          {formatDate(q.created_at)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>

            <div className="px-5 py-4 border-t border-zinc-100 flex justify-end bg-zinc-50/50">
              <button
                onClick={() => { setQueryUser(null); setQueries([]); }}
                className="px-4 py-2 text-xs font-medium text-zinc-600 hover:text-zinc-800 hover:bg-zinc-200/50 rounded-xl transition-colors"
              >
                关闭
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
