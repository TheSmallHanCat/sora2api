import type { Token } from '../types';

export const formatExpiry = (expiry?: string | null): { text: string; className: string } => {
  if (!expiry) return { text: '-', className: '' };

  const date = new Date(expiry);
  const now = new Date();
  const diff = date.getTime() - now.getTime();

  const dateStr = date.toLocaleDateString('ru-RU', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).replace(/\//g, '-');

  const timeStr = date.toLocaleTimeString('ru-RU', {
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  });

  const text = `${dateStr} ${timeStr}`;

  if (diff < 0) {
    return { text, className: 'expired' };
  }

  const days = Math.floor(diff / (1000 * 60 * 60 * 24));
  if (days < 7) {
    return { text, className: 'expiringSoon' };
  }

  return { text, className: '' };
};

export const formatPlanType = (type?: string | null): string => {
  if (!type) return '-';

  const typeMap: Record<string, string> = {
    chatgpt_team: 'Team',
    chatgpt_plus: 'Plus',
    chatgpt_pro: 'Pro',
    chatgpt_free: 'Free',
  };

  return typeMap[type] || type;
};

export const formatSubscriptionEnd = (subscriptionEnd?: string | null): string => {
  if (!subscriptionEnd) return '';

  const date = new Date(subscriptionEnd);
  const dateStr = date.toLocaleDateString('ru-RU', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).replace(/\//g, '-');

  const timeStr = date.toLocaleTimeString('ru-RU', {
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  });

  return `${dateStr} ${timeStr}`;
};

export const formatSora2Tooltip = (token: Token): string => {
  if (token.sora2_supported !== true) return '';

  const remaining = (token.sora2_total_count || 0) - (token.sora2_redeemed_count || 0);
  return `Код приглашения: ${token.sora2_invite_code || 'Нет'}\nДоступно: ${remaining}/${token.sora2_total_count}\nИспользовано раз: ${token.sora2_redeemed_count}`;
};

export const formatClientId = (clientId?: string | null): string => {
  if (!clientId) return '-';
  return `${clientId.substring(0, 8)}...`;
};

export const formatDateTime = (dateStr?: string | null): string => {
  if (!dateStr) return '-';
  return new Date(dateStr).toLocaleString('ru-RU');
};

export const copyToClipboard = async (text: string): Promise<boolean> => {
  try {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      await navigator.clipboard.writeText(text);
      return true;
    } else {
      const textarea = document.createElement('textarea');
      textarea.value = text;
      textarea.style.position = 'fixed';
      textarea.style.opacity = '0';
      document.body.appendChild(textarea);
      textarea.select();
      const success = document.execCommand('copy');
      document.body.removeChild(textarea);
      return success;
    }
  } catch {
    return false;
  }
};
