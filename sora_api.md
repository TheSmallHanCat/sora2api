# Документация API Sora

Основано на анализе `src/services/sora_client.py`.

## Базовая конфигурация
- **Базовый URL**: Настраивается в `config.sora_base_url` (Обычно `https://sora.chatgpt.com`)
- **Заголовки**:
    - `Authorization`: `Bearer {token}`
    - `Content-Type`: `application/json` (если не используется multipart)
    - `openai-sentinel-token`: Обязателен для эндпоинтов генерации/публикации (случайная строка из 10-20 символов)
    - User-Agent/Fingerprint: Обрабатывается `curl_cffi` (имитирует Chrome)

## Эндпоинты

### Информация о пользователе

#### Получить информацию о пользователе
- **Эндпоинт**: `/me`
- **Метод**: `GET`
- **Возвращает**: Профиль пользователя

### Генерация изображений

#### Загрузка изображения (для использования в генерации)
- **Эндпоинт**: `/uploads`
- **Метод**: `POST`
- **Content-Type**: `multipart/form-data`
- **Тело запроса**:
    - `file`: Данные файла изображения (image/png, image/jpeg, image/webp)
    - `file_name`: Имя файла
- **Возвращает**: `{"id": "media_id"}`

#### Генерация изображения
- **Эндпоинт**: `/video_gen`
- **Метод**: `POST`
- **Заголовки**: Требуется `openai-sentinel-token`
- **Тело запроса**:
    ```json
    {
        "type": "image_gen",
        "operation": "simple_compose" | "remix",
        "prompt": "строка",
        "width": 360,
        "height": 360,
        "n_variants": 1,
        "n_frames": 1,
        "inpaint_items": [
            {
                "type": "image",
                "frame_index": 0,
                "upload_media_id": "{media_id}"
            }
        ]
    }
    ```
- **Возвращает**: `{"id": "task_id"}`

#### Получить недавние задачи генерации изображений
- **Эндпоинт**: `/v2/recent_tasks`
- **Метод**: `GET`
- **Параметры запроса**: `limit` (по умолчанию 20)
- **Возвращает**: Список недавних задач

### Генерация видео

#### Генерация видео (Текст-в-Видео / Изображение-в-Видео)
- **Эндпоинт**: `/nf/create`
- **Метод**: `POST`
- **Заголовки**: Требуется `openai-sentinel-token`
- **Тело запроса**:
    ```json
    {
        "kind": "video",
        "prompt": "строка",
        "orientation": "landscape" | "portrait",
        "size": "small",
        "n_frames": 450,
        "model": "sy_8",
        "inpaint_items": [
            {
                "kind": "upload",
                "upload_id": "{media_id}"
            }
        ]
    }
    ```
- **Возвращает**: `{"id": "task_id"}`

#### Генерация видео (Ремикс / Изменение существующего)
- **Эндпоинт**: `/nf/create`
- **Метод**: `POST`
- **Заголовки**: Требуется `openai-sentinel-token`
- **Тело запроса**:
    ```json
    {
        "kind": "video",
        "prompt": "строка",
        "orientation": "portrait" | "landscape",
        "n_frames": 450,
        "model": "sy_8",
        "remix_target_id": "{video_id}",
        "inpaint_items": [],
        "cameo_ids": [],
        "cameo_replacements": {}
    }
    ```
    *(Примечание: `cameo_ids` и `cameo_replacements` в текущей реализации пусты/null)*
- **Возвращает**: `{"id": "task_id"}`

#### Генерация видео в режиме Storyboard (Раскадровка)
- **Эндпоинт**: `/nf/create/storyboard`
- **Метод**: `POST`
- **Заголовки**: Требуется `openai-sentinel-token`
- **Тело запроса**:
    ```json
    {
        "kind": "video",
        "prompt": "current timeline:\nShot 1:...\n\ninstructions:\n...",
        "title": "Draft your video",
        "orientation": "landscape",
        "size": "small",
        "n_frames": 450,
        "model": "sy_8",
        "storyboard_id": null,
        "inpaint_items": [],
        "remix_target_id": null,
        "metadata": null,
        "style_id": null,
        "cameo_ids": null,
        "cameo_replacements": null
    }
    ```
- **Возвращает**: `{"id": "task_id"}`

#### Получить черновики видео
- **Эндпоинт**: `/project_y/profile/drafts`
- **Метод**: `GET`
- **Параметры запроса**: `limit` (по умолчанию 15)
- **Возвращает**: Список черновиков

#### Получить ожидающие задачи
- **Эндпоинт**: `/nf/pending`
- **Метод**: `GET`
- **Возвращает**: Список задач в очереди с прогрессом выполнения

### Публикация и Шеринг

#### Публикация видео (для получения версии без водяного знака)
- **Эндпоинт**: `/project_y/post`
- **Метод**: `POST`
- **Заголовки**: Требуется `openai-sentinel-token`
- **Тело запроса**:
    ```json
    {
        "attachments_to_create": [
            {
                "generation_id": "{generation_id}",
                "kind": "sora"
            }
        ],
        "post_text": ""
    }
    ```
- **Возвращает**: `{"post": {"id": "post_id"}}`

#### Удаление поста
- **Эндпоинт**: `/project_y/post/{post_id}`
- **Метод**: `DELETE`
- **Возвращает**: 200/204 OK

### Персонализация персонажей (Cameos)

#### Загрузка видео персонажа
- **Эндпоинт**: `/characters/upload`
- **Метод**: `POST`
- **Content-Type**: `multipart/form-data`
- **Тело запроса**:
    - `file`: Видео файл (video/mp4)
    - `timestamps`: `b"0,3"`
- **Возвращает**: `{"id": "cameo_id"}`

#### Получить статус обработки персонажа
- **Эндпоинт**: `/project_y/cameos/in_progress/{cameo_id}`
- **Метод**: `GET`
- **Возвращает**: Объект статуса

#### Загрузка изображения профиля персонажа
- **Эндпоинт**: `/project_y/file/upload`
- **Метод**: `POST`
- **Content-Type**: `multipart/form-data`
- **Тело запроса**:
    - `file`: Файл изображения (image/webp)
    - `use_case`: `b"profile"`
- **Возвращает**: `{"asset_pointer": "string"}`

#### Финализация создания персонажа
- **Эндпоинт**: `/characters/finalize`
- **Метод**: `POST`
- **Тело запроса**:
    ```json
    {
        "cameo_id": "string",
        "username": "string",
        "display_name": "string",
        "profile_asset_pointer": "string",
        "instruction_set": null,
        "safety_instruction_set": null
    }
    ```
- **Возвращает**: `{"character": {"character_id": "string"}}`

#### Сделать персонажа публичным
- **Эндпоинт**: `/project_y/cameos/by_id/{cameo_id}/update_v2`
- **Метод**: `POST`
- **Тело запроса**: `{"visibility": "public"}`

#### Удаление персонажа
- **Эндпоинт**: `/project_y/characters/{character_id}`
- **Метод**: `DELETE`
