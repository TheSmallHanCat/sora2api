import React, { useState, useEffect } from 'react';
import { Button, Input, Toggle, Select } from '../common';
import { api } from '../../services/api';
import { useToast } from '../../context/ToastContext';
import type {
  AdminConfig,
  ProxyConfig,
  WatermarkFreeConfig,
  CacheConfig,
  GenerationTimeoutConfig,
} from '../../types';
import styles from './SettingsPanel.module.css';

export const SettingsPanel: React.FC = () => {
  const { showToast } = useToast();

  // Admin config
  const [adminUsername, setAdminUsername] = useState('');
  const [oldPassword, setOldPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [currentApiKey, setCurrentApiKey] = useState('');
  const [newApiKey, setNewApiKey] = useState('');
  const [errorBan, setErrorBan] = useState('3');
  const [debugEnabled, setDebugEnabled] = useState(false);

  // Proxy config
  const [proxyEnabled, setProxyEnabled] = useState(false);
  const [proxyUrl, setProxyUrl] = useState('');

  // Watermark free config
  const [watermarkFreeEnabled, setWatermarkFreeEnabled] = useState(false);
  const [parseMethod, setParseMethod] = useState<'third_party' | 'custom'>('third_party');
  const [customParseUrl, setCustomParseUrl] = useState('');
  const [customParseToken, setCustomParseToken] = useState('');

  // Cache config
  const [cacheEnabled, setCacheEnabled] = useState(false);
  const [cacheTimeout, setCacheTimeout] = useState('7200');
  const [cacheBaseUrl, setCacheBaseUrl] = useState('');
  const [effectiveBaseUrl, setEffectiveBaseUrl] = useState('');

  // Generation timeout config
  const [imageTimeout, setImageTimeout] = useState('300');
  const [videoTimeout, setVideoTimeout] = useState('1500');

  useEffect(() => {
    loadAllConfigs();
  }, []);

  const loadAllConfigs = async () => {
    try {
      const [adminRes, proxyRes, watermarkRes, cacheRes, timeoutRes] = await Promise.all([
        api.getAdminConfig(),
        api.getProxyConfig(),
        api.getWatermarkFreeConfig(),
        api.getCacheConfig(),
        api.getGenerationTimeout(),
      ]);

      // Admin config
      setAdminUsername((adminRes as AdminConfig).admin_username || 'admin');
      setCurrentApiKey((adminRes as AdminConfig).api_key || '');
      setErrorBan(String((adminRes as AdminConfig).error_ban_threshold || 3));
      setDebugEnabled((adminRes as AdminConfig).debug_enabled || false);

      // Proxy config
      setProxyEnabled((proxyRes as ProxyConfig).proxy_enabled || false);
      setProxyUrl((proxyRes as ProxyConfig).proxy_url || '');

      // Watermark free config
      setWatermarkFreeEnabled((watermarkRes as WatermarkFreeConfig).watermark_free_enabled || false);
      setParseMethod((watermarkRes as WatermarkFreeConfig).parse_method || 'third_party');
      setCustomParseUrl((watermarkRes as WatermarkFreeConfig).custom_parse_url || '');
      setCustomParseToken((watermarkRes as WatermarkFreeConfig).custom_parse_token || '');

      // Cache config
      if (cacheRes.success && cacheRes.config) {
        const config = cacheRes.config as CacheConfig;
        setCacheEnabled(config.enabled !== false);
        setCacheTimeout(String(config.timeout || 7200));
        setCacheBaseUrl(config.base_url || '');
        setEffectiveBaseUrl(config.effective_base_url || '');
      }

      // Generation timeout config
      if (timeoutRes.success && timeoutRes.config) {
        const config = timeoutRes.config as GenerationTimeoutConfig;
        setImageTimeout(String(config.image_timeout || 300));
        setVideoTimeout(String(config.video_timeout || 1500));
      }
    } catch (err) {
      console.error('Error loading configs:', err);
    }
  };

  const handleUpdatePassword = async () => {
    if (!oldPassword || !newPassword) {
      showToast('Пожалуйста, введите старый пароль и новый пароль', 'error');
      return;
    }
    if (newPassword.length < 4) {
      showToast('Новый пароль должен содержать не менее 4 символов', 'error');
      return;
    }
    try {
      const result = await api.updatePassword({
        username: adminUsername || undefined,
        old_password: oldPassword,
        new_password: newPassword,
      });
      if (result.success) {
        showToast('Пароль успешно изменен, пожалуйста, войдите снова', 'success');
        setTimeout(() => {
          api.logout();
        }, 2000);
      } else {
        showToast(`Ошибка изменения: ${result.detail || 'Неизвестная ошибка'}`, 'error');
      }
    } catch (err) {
      showToast(`Ошибка изменения: ${err instanceof Error ? err.message : 'Неизвестная ошибка'}`, 'error');
    }
  };

  const handleUpdateApiKey = async () => {
    if (!newApiKey) {
      showToast('Пожалуйста, введите новый API ключ', 'error');
      return;
    }
    if (newApiKey.length < 6) {
      showToast('API ключ должен содержать не менее 6 символов', 'error');
      return;
    }
    if (!window.confirm('Вы уверены, что хотите обновить API ключ? После обновления необходимо уведомить всех клиентов об использовании нового ключа.')) {
      return;
    }
    try {
      const result = await api.updateApiKey(newApiKey);
      if (result.success) {
        showToast('API ключ успешно обновлен', 'success');
        setCurrentApiKey(newApiKey);
        setNewApiKey('');
      } else {
        showToast(`Ошибка обновления: ${result.detail || 'Неизвестная ошибка'}`, 'error');
      }
    } catch (err) {
      showToast(`Ошибка обновления: ${err instanceof Error ? err.message : 'Неизвестная ошибка'}`, 'error');
    }
  };

  const handleSaveAdminConfig = async () => {
    try {
      const result = await api.saveAdminConfig({
        error_ban_threshold: parseInt(errorBan) || 3,
      });
      if (result.success) {
        showToast('Конфигурация успешно сохранена', 'success');
      } else {
        showToast('Ошибка сохранения', 'error');
      }
    } catch (err) {
      showToast(`Ошибка сохранения: ${err instanceof Error ? err.message : 'Неизвестная ошибка'}`, 'error');
    }
  };

  const handleToggleDebug = async (enabled: boolean) => {
    try {
      const result = await api.toggleDebug(enabled);
      if (result.success) {
        setDebugEnabled(enabled);
        showToast(enabled ? 'Режим отладки включен' : 'Режим отладки выключен', 'success');
      } else {
        showToast(`Ошибка операции: ${result.detail || 'Неизвестная ошибка'}`, 'error');
      }
    } catch (err) {
      showToast(`Ошибка операции: ${err instanceof Error ? err.message : 'Неизвестная ошибка'}`, 'error');
    }
  };

  const handleSaveProxyConfig = async () => {
    try {
      const result = await api.saveProxyConfig({
        proxy_enabled: proxyEnabled,
        proxy_url: proxyUrl,
      });
      if (result.success) {
        showToast('Настройка прокси успешно сохранена', 'success');
      } else {
        showToast('Ошибка сохранения', 'error');
      }
    } catch (err) {
      showToast(`Ошибка сохранения: ${err instanceof Error ? err.message : 'Неизвестная ошибка'}`, 'error');
    }
  };

  const handleSaveWatermarkFreeConfig = async () => {
    if (watermarkFreeEnabled && parseMethod === 'custom') {
      if (!customParseUrl) {
        showToast('Пожалуйста, введите адрес сервера разбора', 'error');
        return;
      }
      if (!customParseToken) {
        showToast('Пожалуйста, введите ключ доступа', 'error');
        return;
      }
    }
    try {
      const result = await api.saveWatermarkFreeConfig({
        watermark_free_enabled: watermarkFreeEnabled,
        parse_method: parseMethod,
        custom_parse_url: customParseUrl || null,
        custom_parse_token: customParseToken || null,
      });
      if (result.success) {
        showToast('Настройка режима без водяных знаков успешно сохранена', 'success');
      } else {
        showToast('Ошибка сохранения', 'error');
      }
    } catch (err) {
      showToast(`Ошибка сохранения: ${err instanceof Error ? err.message : 'Неизвестная ошибка'}`, 'error');
    }
  };

  const handleSaveCacheConfig = async () => {
    const timeout = parseInt(cacheTimeout);
    if (timeout < 60 || timeout > 86400) {
      showToast('Время хранения кэша должно быть в диапазоне 60-86400 секунд', 'error');
      return;
    }
    if (cacheBaseUrl && !cacheBaseUrl.startsWith('http://') && !cacheBaseUrl.startsWith('https://')) {
      showToast('Домен должен начинаться с http:// или https://', 'error');
      return;
    }
    try {
      await api.saveCacheEnabled(cacheEnabled);
      await api.saveCacheTimeout(timeout);
      await api.saveCacheBaseUrl(cacheBaseUrl);
      showToast('Настройка кэша успешно сохранена', 'success');
      // Reload cache config to get effective URL
      const cacheRes = await api.getCacheConfig();
      if (cacheRes.success && cacheRes.config) {
        setEffectiveBaseUrl(cacheRes.config.effective_base_url || '');
      }
    } catch (err) {
      showToast(`Ошибка сохранения: ${err instanceof Error ? err.message : 'Неизвестная ошибка'}`, 'error');
    }
  };

  const handleSaveGenerationTimeout = async () => {
    const imgTimeout = parseInt(imageTimeout);
    const vidTimeout = parseInt(videoTimeout);
    if (imgTimeout < 60 || imgTimeout > 3600) {
      showToast('Время ожидания изображения должно быть в диапазоне 60-3600 секунд', 'error');
      return;
    }
    if (vidTimeout < 60 || vidTimeout > 7200) {
      showToast('Время ожидания видео должно быть в диапазоне 60-7200 секунд', 'error');
      return;
    }
    try {
      const result = await api.saveGenerationTimeout({
        image_timeout: imgTimeout,
        video_timeout: vidTimeout,
      });
      if (result.success) {
        showToast('Настройка таймаутов генерации успешно сохранена', 'success');
      } else {
        showToast('Ошибка сохранения', 'error');
      }
    } catch (err) {
      showToast(`Ошибка сохранения: ${err instanceof Error ? err.message : 'Неизвестная ошибка'}`, 'error');
    }
  };

  return (
    <div className={styles.grid}>
      {/* Security Settings */}
      <div className={styles.card}>
        <h3 className={styles.cardTitle}>Настройки безопасности</h3>
        <div className={styles.cardContent}>
          <div className={styles.field}>
            <label className={styles.label}>Имя администратора</label>
            <Input
              value={adminUsername}
              onChange={(e) => setAdminUsername(e.target.value)}
            />
            <p className={styles.hint}>Имя администратора</p>
          </div>
          <div className={styles.field}>
            <label className={styles.label}>Старый пароль</label>
            <Input
              type="password"
              value={oldPassword}
              onChange={(e) => setOldPassword(e.target.value)}
              placeholder="Введите старый пароль"
            />
          </div>
          <div className={styles.field}>
            <label className={styles.label}>Новый пароль</label>
            <Input
              type="password"
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              placeholder="Введите новый пароль"
            />
          </div>
          <Button fullWidth onClick={handleUpdatePassword}>
            Изменить пароль
          </Button>
        </div>
      </div>

      {/* API Key Settings */}
      <div className={styles.card}>
        <h3 className={styles.cardTitle}>Настройка API ключа</h3>
        <div className={styles.cardContent}>
          <div className={styles.field}>
            <label className={styles.label}>Текущий API ключ</label>
            <Input value={currentApiKey} disabled />
            <p className={styles.hint}>Используемый API ключ (только чтение)</p>
          </div>
          <div className={styles.field}>
            <label className={styles.label}>Новый API ключ</label>
            <Input
              value={newApiKey}
              onChange={(e) => setNewApiKey(e.target.value)}
              placeholder="Введите новый API ключ"
            />
            <p className={styles.hint}>Ключ для вызова API клиентом</p>
          </div>
          <Button fullWidth onClick={handleUpdateApiKey}>
            Обновить API ключ
          </Button>
        </div>
      </div>

      {/* Proxy Settings */}
      <div className={styles.card}>
        <h3 className={styles.cardTitle}>Настройка прокси</h3>
        <div className={styles.cardContent}>
          <div className={styles.field}>
            <Toggle
              checked={proxyEnabled}
              onChange={setProxyEnabled}
              label="Включить прокси"
            />
          </div>
          <div className={styles.field}>
            <label className={styles.label}>Адрес прокси</label>
            <Input
              value={proxyUrl}
              onChange={(e) => setProxyUrl(e.target.value)}
              placeholder="http://127.0.0.1:7890 или socks5://127.0.0.1:1080"
            />
            <p className={styles.hint}>Поддержка HTTP и SOCKS5 прокси</p>
          </div>
          <Button fullWidth onClick={handleSaveProxyConfig}>
            Сохранить настройки
          </Button>
        </div>
      </div>

      {/* Error Handling Settings */}
      <div className={styles.card}>
        <h3 className={styles.cardTitle}>Настройки обработки ошибок</h3>
        <div className={styles.cardContent}>
          <div className={styles.field}>
            <label className={styles.label}>Порог блокировки по ошибкам</label>
            <Input
              type="number"
              value={errorBan}
              onChange={(e) => setErrorBan(e.target.value)}
              placeholder="3"
            />
            <p className={styles.hint}>Автоматическая блокировка Token при достижении числа последовательных ошибок</p>
          </div>
          <Button fullWidth onClick={handleSaveAdminConfig}>
            Сохранить настройки
          </Button>
        </div>
      </div>

      {/* Cache Settings */}
      <div className={styles.card}>
        <h3 className={styles.cardTitle}>Настройка кэша</h3>
        <div className={styles.cardContent}>
          <div className={styles.field}>
            <Toggle
              checked={cacheEnabled}
              onChange={setCacheEnabled}
              label="Включить кэш"
            />
            <p className={styles.hint}>При отключении сгенерированные изображения и видео будут выводиться напрямую ссылкой, без кэширования</p>
          </div>
          {cacheEnabled && (
            <>
              <div className={styles.field}>
                <label className={styles.label}>Время хранения кэша (секунд)</label>
                <Input
                  type="number"
                  value={cacheTimeout}
                  onChange={(e) => setCacheTimeout(e.target.value)}
                  placeholder="7200"
                  min={60}
                  max={86400}
                />
                <p className={styles.hint}>Время хранения файлов, диапазон: 60-86400 секунд (1 минута - 24 часа)</p>
              </div>
              <div className={styles.field}>
                <label className={styles.label}>Домен для доступа к кэшу</label>
                <Input
                  value={cacheBaseUrl}
                  onChange={(e) => setCacheBaseUrl(e.target.value)}
                  placeholder="https://yourdomain.com"
                />
                <p className={styles.hint}>Оставьте пустым для использования адреса сервера, например: https://yourdomain.com</p>
              </div>
              {effectiveBaseUrl && (
                <div className={styles.infoBox}>
                  <p className={styles.infoText}>
                    <strong>Текущий адрес доступа:</strong>{' '}
                    <code className={styles.code}>{effectiveBaseUrl}</code>
                  </p>
                </div>
              )}
            </>
          )}
          <Button fullWidth onClick={handleSaveCacheConfig}>
            Сохранить конфигурацию
          </Button>
        </div>
      </div>

      {/* Generation Timeout Settings */}
      <div className={styles.card}>
        <h3 className={styles.cardTitle}>Настройка таймаутов генерации</h3>
        <div className={styles.cardContent}>
          <div className={styles.field}>
            <label className={styles.label}>Таймаут генерации изображений (секунды)</label>
            <Input
              type="number"
              value={imageTimeout}
              onChange={(e) => setImageTimeout(e.target.value)}
              placeholder="300"
              min={60}
              max={3600}
            />
            <p className={styles.hint}>Таймаут генерации изображений, диапазон: 60-3600 секунд (1 минута - 1 час), после таймаута автоматически освобождается блокировка Token</p>
          </div>
          <div className={styles.field}>
            <label className={styles.label}>Таймаут генерации видео (секунды)</label>
            <Input
              type="number"
              value={videoTimeout}
              onChange={(e) => setVideoTimeout(e.target.value)}
              placeholder="1500"
              min={60}
              max={7200}
            />
            <p className={styles.hint}>Таймаут генерации видео, диапазон: 60-7200 секунд (1 минута - 2 часа), после таймаута возвращается ошибка таймаута вышестоящего API</p>
          </div>
          <Button fullWidth onClick={handleSaveGenerationTimeout}>
            Сохранить конфигурацию
          </Button>
        </div>
      </div>

      {/* Watermark Free Settings */}
      <div className={styles.card}>
        <h3 className={styles.cardTitle}>Настройка режима без водяных знаков</h3>
        <div className={styles.cardContent}>
          <div className={styles.field}>
            <Toggle
              checked={watermarkFreeEnabled}
              onChange={setWatermarkFreeEnabled}
              label="Включить режим без водяных знаков"
            />
            <p className={styles.hint}>При включении сгенерированное видео будет опубликовано на платформе Sora, извлечено без водяного знака, а после кэширования автоматически удалено</p>
          </div>
          {watermarkFreeEnabled && (
            <>
              <div className={styles.field}>
                <label className={styles.label}>Метод парсинга</label>
                <Select
                  value={parseMethod}
                  onChange={(e) => setParseMethod(e.target.value as 'third_party' | 'custom')}
                  options={[
                    { value: 'third_party', label: 'Сторонний парсинг' },
                    { value: 'custom', label: 'Пользовательский интерфейс парсинга' },
                  ]}
                />
              </div>
              {parseMethod === 'custom' && (
                <>
                  <div className={styles.field}>
                    <label className={styles.label}>Адрес сервера парсинга</label>
                    <Input
                      value={customParseUrl}
                      onChange={(e) => setCustomParseUrl(e.target.value)}
                      placeholder="Введите адрес сервера (например: http://example.com)"
                    />
                    <p className={styles.hint}>
                      <a
                        href="https://github.com/tibbar213/sora-downloader"
                        target="_blank"
                        rel="noopener noreferrer"
                        className={styles.link}
                      >
                        Развернуть собственный сервер парсинга
                      </a>
                    </p>
                  </div>
                  <div className={styles.field}>
                    <label className={styles.label}>Ключ доступа (опционально)</label>
                    <Input
                      type="password"
                      value={customParseToken}
                      onChange={(e) => setCustomParseToken(e.target.value)}
                      placeholder="Введите ключ доступа"
                    />
                  </div>
                </>
              )}
            </>
          )}
          <Button fullWidth onClick={handleSaveWatermarkFreeConfig}>
            Сохранить настройки
          </Button>
        </div>
      </div>

      {/* Debug Settings */}
      <div className={styles.card}>
        <h3 className={styles.cardTitle}>Настройки отладки</h3>
        <div className={styles.cardContent}>
          <div className={styles.field}>
            <Toggle
              checked={debugEnabled}
              onChange={handleToggleDebug}
              label="Включить режим отладки"
            />
            <p className={styles.hint}>
              При включении подробные логи запросов и ответов API будут записываться в файл{' '}
              <code className={styles.code}>logs.txt</code>, требуется перезапуск
            </p>
          </div>
          <div className={styles.warningBox}>
            <p className={styles.warningText}>
              <strong>Внимание:</strong> Режим отладки генерирует очень большой объем логов, используйте только при отладке
            </p>
          </div>
        </div>
      </div>
    </div>
  );
};
