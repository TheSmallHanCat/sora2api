import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import { useToast } from '../../context/ToastContext';
import { Header, Footer } from '../../components/layout';
import { Button, Toggle } from '../../components/common';
import {
  StatsCards,
  TokenTable,
  AddTokenModal,
  EditTokenModal,
  ImportModal,
  Sora2Modal,
} from '../../components/tokens';
import { SettingsPanel } from '../../components/settings';
import { LogsPanel } from '../../components/logs';
import { api } from '../../services/api';
import { copyToClipboard } from '../../utils/formatters';
import type { Token, Stats, TabType } from '../../types';
import styles from './Manage.module.css';

export const Manage: React.FC = () => {
  const [activeTab, setActiveTab] = useState<TabType>('tokens');
  const [tokens, setTokens] = useState<Token[]>([]);
  const [stats, setStats] = useState<Stats | null>(null);
  const [atAutoRefresh, setAtAutoRefresh] = useState(false);

  // Modals
  const [addModalOpen, setAddModalOpen] = useState(false);
  const [editModalOpen, setEditModalOpen] = useState(false);
  const [importModalOpen, setImportModalOpen] = useState(false);
  const [sora2ModalOpen, setSora2ModalOpen] = useState(false);
  const [editingToken, setEditingToken] = useState<Token | null>(null);
  const [sora2TokenId, setSora2TokenId] = useState<number | null>(null);

  const { isAuthenticated, isLoading } = useAuth();
  const { showToast } = useToast();
  const navigate = useNavigate();

  useEffect(() => {
    if (!isLoading && !isAuthenticated) {
      navigate('/login');
    }
  }, [isAuthenticated, isLoading, navigate]);

  const loadTokens = useCallback(async () => {
    try {
      const data = await api.getTokens();
      setTokens(data);
    } catch (err) {
      console.error('Error loading tokens:', err);
    }
  }, []);

  const loadStats = useCallback(async () => {
    try {
      const data = await api.getStats();
      setStats(data);
    } catch (err) {
      console.error('Error loading stats:', err);
    }
  }, []);

  const loadAtAutoRefreshConfig = useCallback(async () => {
    try {
      const result = await api.getTokenRefreshConfig();
      if (result.success && result.config) {
        setAtAutoRefresh(result.config.at_auto_refresh_enabled || false);
      }
    } catch (err) {
      console.error('Error loading AT auto refresh config:', err);
    }
  }, []);

  const refreshTokens = useCallback(async () => {
    await Promise.all([loadTokens(), loadStats()]);
  }, [loadTokens, loadStats]);

  useEffect(() => {
    if (isAuthenticated) {
      refreshTokens();
      loadAtAutoRefreshConfig();
    }
  }, [isAuthenticated, refreshTokens, loadAtAutoRefreshConfig]);

  const handleToggleAtAutoRefresh = async (enabled: boolean) => {
    try {
      const result = await api.toggleTokenRefresh(enabled);
      if (result.success) {
        setAtAutoRefresh(enabled);
        showToast(
          enabled ? 'Автоматическое обновление AT включено' : 'Автоматическое обновление AT выключено',
          'success'
        );
      } else {
        showToast(`Ошибка операции: ${result.detail || 'Неизвестная ошибка'}`, 'error');
      }
    } catch (err) {
      showToast(`Ошибка операции: ${err instanceof Error ? err.message : 'Неизвестная ошибка'}`, 'error');
    }
  };

  const handleTestToken = async (id: number) => {
    try {
      showToast('Тестирование Token...', 'info');
      const result = await api.testToken(id);
      if (result.success && result.status === 'success') {
        let msg = `Token действителен! Пользователь: ${result.email || 'Неизвестно'}`;
        if (result.sora2_supported) {
          const remaining = (result.sora2_total_count || 0) - (result.sora2_redeemed_count || 0);
          msg += `\nSora2: Поддерживается (${remaining}/${result.sora2_total_count})`;
          if (result.sora2_remaining_count !== undefined) {
            msg += `\nДоступно: ${result.sora2_remaining_count}`;
          }
        }
        showToast(msg, 'success');
        await refreshTokens();
      } else {
        showToast(`Token недействителен: ${result.message || 'Неизвестная ошибка'}`, 'error');
      }
    } catch (err) {
      showToast(`Ошибка теста: ${err instanceof Error ? err.message : 'Неизвестная ошибка'}`, 'error');
    }
  };

  const handleEditToken = (token: Token) => {
    setEditingToken(token);
    setEditModalOpen(true);
  };

  const handleToggleToken = async (id: number, isActive: boolean) => {
    try {
      const result = isActive ? await api.disableToken(id) : await api.enableToken(id);
      if (result.success) {
        await refreshTokens();
        showToast(isActive ? 'Token отключён' : 'Token включён', 'success');
      } else {
        showToast('Ошибка действия', 'error');
      }
    } catch (err) {
      showToast(`Ошибка действия: ${err instanceof Error ? err.message : 'Неизвестная ошибка'}`, 'error');
    }
  };

  const handleDeleteToken = async (id: number) => {
    if (!window.confirm('Вы уверены, что хотите удалить этот Token?')) {
      return;
    }
    try {
      const result = await api.deleteToken(id);
      if (result.success) {
        await refreshTokens();
        showToast('Успешно удалено', 'success');
      } else {
        showToast('Ошибка удаления', 'error');
      }
    } catch (err) {
      showToast(`Ошибка удаления: ${err instanceof Error ? err.message : 'Неизвестная ошибка'}`, 'error');
    }
  };

  const handleSora2Activate = (id: number) => {
    setSora2TokenId(id);
    setSora2ModalOpen(true);
  };

  const handleCopySora2Code = async (code: string) => {
    if (!code) {
      showToast('Нет кода приглашения для копирования', 'error');
      return;
    }
    const success = await copyToClipboard(code);
    if (success) {
      showToast(`Код приглашения скопирован: ${code}`, 'success');
    } else {
      showToast('Ошибка копирования: браузер не поддерживается', 'error');
    }
  };

  const handleExportTokens = () => {
    if (tokens.length === 0) {
      showToast('Нет токенов для экспорта', 'error');
      return;
    }
    const exportData = tokens.map((t) => ({
      email: t.email,
      access_token: t.token,
      session_token: t.st || null,
      refresh_token: t.rt || null,
      is_active: t.is_active,
      image_enabled: t.image_enabled !== false,
      video_enabled: t.video_enabled !== false,
      image_concurrency: t.image_concurrency || -1,
      video_concurrency: t.video_concurrency || -1,
    }));
    const dataStr = JSON.stringify(exportData, null, 2);
    const dataBlob = new Blob([dataStr], { type: 'application/json' });
    const url = URL.createObjectURL(dataBlob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `tokens_${new Date().toISOString().split('T')[0]}.json`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
    showToast(`Экспортировано ${tokens.length} токенов`, 'success');
  };

  const handleTabChange = (tab: TabType) => {
    setActiveTab(tab);
  };

  if (isLoading) {
    return (
      <div className={styles.loadingContainer}>
        <div className={styles.loadingSpinner} />
      </div>
    );
  }

  return (
    <div className={styles.container}>
      <Header />
      <main className={styles.main}>
        {/* Tab Navigation */}
        <div className={styles.tabNav}>
          <nav className={styles.tabs}>
            <button
              className={`${styles.tabBtn} ${activeTab === 'tokens' ? styles.tabActive : ''}`}
              onClick={() => handleTabChange('tokens')}
            >
              Управление Token
            </button>
            <button
              className={`${styles.tabBtn} ${activeTab === 'settings' ? styles.tabActive : ''}`}
              onClick={() => handleTabChange('settings')}
            >
              Настройки системы
            </button>
            <button
              className={`${styles.tabBtn} ${activeTab === 'logs' ? styles.tabActive : ''}`}
              onClick={() => handleTabChange('logs')}
            >
              Журнал запросов
            </button>
          </nav>
        </div>

        {/* Tokens Panel */}
        {activeTab === 'tokens' && (
          <div>
            <StatsCards stats={stats} />
            <div className={styles.tokenCard}>
              <div className={styles.tokenHeader}>
                <h3 className={styles.tokenTitle}>Список Token</h3>
                <div className={styles.tokenActions}>
                  <div className={styles.autoRefreshToggle}>
                    <span className={styles.autoRefreshLabel}>Автообновление AT</span>
                    <div className={styles.toggleWrapper} title="Когда до истечения Token <24ч, автоматически обновлять AT используя ST или RT">
                      <Toggle
                        checked={atAutoRefresh}
                        onChange={handleToggleAtAutoRefresh}
                      />
                    </div>
                  </div>
                  <button className={styles.iconBtn} onClick={refreshTokens} title="Обновить">
                    <svg
                      className={styles.icon}
                      xmlns="http://www.w3.org/2000/svg"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="2"
                    >
                      <polyline points="23 4 23 10 17 10" />
                      <polyline points="1 20 1 14 7 14" />
                      <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15" />
                    </svg>
                  </button>
                  <Button variant="blue" size="sm" onClick={handleExportTokens}>
                    <svg
                      className={styles.btnIcon}
                      xmlns="http://www.w3.org/2000/svg"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="2"
                    >
                      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                      <polyline points="7 10 12 15 17 10" />
                      <line x1="12" y1="15" x2="12" y2="3" />
                    </svg>
                    Экспорт
                  </Button>
                  <Button variant="green" size="sm" onClick={() => setImportModalOpen(true)}>
                    <svg
                      className={styles.btnIcon}
                      xmlns="http://www.w3.org/2000/svg"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="2"
                    >
                      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                      <polyline points="17 8 12 3 7 8" />
                      <line x1="12" y1="3" x2="12" y2="15" />
                    </svg>
                    Импорт
                  </Button>
                  <Button size="sm" onClick={() => setAddModalOpen(true)}>
                    <svg
                      className={styles.btnIcon}
                      xmlns="http://www.w3.org/2000/svg"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="2"
                    >
                      <line x1="12" y1="5" x2="12" y2="19" />
                      <line x1="5" y1="12" x2="19" y2="12" />
                    </svg>
                    Добавить
                  </Button>
                </div>
              </div>
              <TokenTable
                tokens={tokens}
                onTest={handleTestToken}
                onEdit={handleEditToken}
                onToggle={handleToggleToken}
                onDelete={handleDeleteToken}
                onSora2Activate={handleSora2Activate}
                onCopySora2Code={handleCopySora2Code}
              />
            </div>
          </div>
        )}

        {/* Settings Panel */}
        {activeTab === 'settings' && <SettingsPanel />}

        {/* Logs Panel */}
        {activeTab === 'logs' && <LogsPanel />}

        <Footer />
      </main>

      {/* Modals */}
      <AddTokenModal
        isOpen={addModalOpen}
        onClose={() => setAddModalOpen(false)}
        onSuccess={refreshTokens}
      />
      <EditTokenModal
        isOpen={editModalOpen}
        onClose={() => {
          setEditModalOpen(false);
          setEditingToken(null);
        }}
        onSuccess={refreshTokens}
        token={editingToken}
      />
      <ImportModal
        isOpen={importModalOpen}
        onClose={() => setImportModalOpen(false)}
        onSuccess={refreshTokens}
      />
      <Sora2Modal
        isOpen={sora2ModalOpen}
        onClose={() => {
          setSora2ModalOpen(false);
          setSora2TokenId(null);
        }}
        onSuccess={refreshTokens}
        tokenId={sora2TokenId}
      />
    </div>
  );
};
