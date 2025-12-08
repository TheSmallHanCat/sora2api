import React from 'react';
import type { Token } from '../../types';
import { formatExpiry, formatPlanType, formatClientId, formatSora2Tooltip, formatSubscriptionEnd, copyToClipboard } from '../../utils/formatters';
import { useToast } from '../../context/ToastContext';
import styles from './TokenTable.module.css';

interface TokenTableProps {
  tokens: Token[];
  onTest: (id: number) => void;
  onEdit: (token: Token) => void;
  onToggle: (id: number, isActive: boolean) => void;
  onDelete: (id: number) => void;
  onSora2Activate: (id: number) => void;
  onCopySora2Code: (code: string) => void;
}

export const TokenTable: React.FC<TokenTableProps> = ({
  tokens,
  onTest,
  onEdit,
  onToggle,
  onDelete,
  onSora2Activate,
  onCopySora2Code,
}) => {
  const { showToast } = useToast();

  const handleCopyClientId = async (clientId: string) => {
    const success = await copyToClipboard(clientId);
    if (success) {
      showToast('Скопировано', 'success');
    }
  };

  const renderSora2 = (token: Token) => {
    if (token.sora2_supported === true) {
      const remaining = (token.sora2_total_count || 0) - (token.sora2_redeemed_count || 0);
      const tooltip = formatSora2Tooltip(token);
      return (
        <div className={styles.sora2Container}>
          <span
            className={`${styles.badge} ${styles.badgeGreen}`}
            title={tooltip}
            onClick={() => onCopySora2Code(token.sora2_invite_code || '')}
          >
            Поддерживается
          </span>
          <span className={styles.sora2Count} title={tooltip}>
            {remaining}/{token.sora2_total_count}
          </span>
        </div>
      );
    } else if (token.sora2_supported === false) {
      return (
        <span
          className={`${styles.badge} ${styles.badgeGray}`}
          title="Нажмите для активации с помощью кода приглашения"
          onClick={() => onSora2Activate(token.id)}
        >
          Не поддерживается
        </span>
      );
    }
    return '-';
  };

  const renderSora2Remaining = (token: Token) => {
    if (token.sora2_supported === true) {
      return <span className={styles.smallText}>{token.sora2_remaining_count || 0}</span>;
    }
    return '-';
  };

  return (
    <div className={styles.tableWrapper}>
      <table className={styles.table}>
        <thead>
          <tr className={styles.headerRow}>
            <th className={styles.th}>Email</th>
            <th className={styles.th}>Статус</th>
            <th className={styles.th}>Client ID</th>
            <th className={styles.th}>Истекает</th>
            <th className={styles.th}>Тип аккаунта</th>
            <th className={styles.th}>Sora2</th>
            <th className={styles.th}>Доступно</th>
            <th className={styles.th}>Изображения</th>
            <th className={styles.th}>Видео</th>
            <th className={styles.th}>Ошибки</th>
            <th className={styles.th}>Примечание</th>
            <th className={`${styles.th} ${styles.thRight}`}>Действия</th>
          </tr>
        </thead>
        <tbody className={styles.tbody}>
          {tokens.map((token) => {
            const expiry = formatExpiry(token.expiry_time);
            const imageDisplay = token.image_enabled ? token.image_count || 0 : '-';
            const videoDisplay = token.video_enabled && token.sora2_supported ? token.video_count || 0 : '-';

            return (
              <tr key={token.id}>
                <td className={styles.td}>{token.email}</td>
                <td className={styles.td}>
                  <span className={`${styles.badge} ${token.is_active ? styles.badgeGreen : styles.badgeGray}`}>
                    {token.is_active ? 'Активен' : 'Отключен'}
                  </span>
                </td>
                <td className={styles.td}>
                  {token.client_id ? (
                    <span
                      className={styles.clientId}
                      title={token.client_id}
                      onClick={() => handleCopyClientId(token.client_id!)}
                    >
                      {formatClientId(token.client_id)}
                    </span>
                  ) : (
                    '-'
                  )}
                </td>
                <td className={`${styles.td} ${styles.smallText}`}>
                  <span className={expiry.className ? styles[expiry.className] : ''}>
                    {expiry.text}
                  </span>
                </td>
                <td className={`${styles.td} ${styles.smallText}`}>
                  <span
                    className={`${styles.badge} ${styles.badgeBlue}`}
                    title={token.subscription_end ? `Срок действия пакета: ${formatSubscriptionEnd(token.subscription_end)}` : token.plan_title || '-'}
                  >
                    {formatPlanType(token.plan_type)}
                  </span>
                </td>
                <td className={`${styles.td} ${styles.smallText}`}>{renderSora2(token)}</td>
                <td className={styles.td}>{renderSora2Remaining(token)}</td>
                <td className={styles.td}>{imageDisplay}</td>
                <td className={styles.td}>{videoDisplay}</td>
                <td className={styles.td}>{token.error_count || 0}</td>
                <td className={`${styles.td} ${styles.smallText} ${styles.muted}`}>
                  {token.remark || '-'}
                </td>
                <td className={`${styles.td} ${styles.tdRight}`}>
                  <button
                    className={`${styles.actionBtn} ${styles.actionBlue}`}
                    onClick={() => onTest(token.id)}
                  >
                    Тест
                  </button>
                  <button
                    className={`${styles.actionBtn} ${styles.actionGreen}`}
                    onClick={() => onEdit(token)}
                  >
                    Редактировать
                  </button>
                  <button
                    className={styles.actionBtn}
                    onClick={() => onToggle(token.id, token.is_active)}
                  >
                    {token.is_active ? 'Отключить' : 'Включить'}
                  </button>
                  <button
                    className={`${styles.actionBtn} ${styles.actionDanger}`}
                    onClick={() => onDelete(token.id)}
                  >
                    Удалить
                  </button>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
};
