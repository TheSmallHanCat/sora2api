import axios from 'axios';
import type { Account, Model, ChatCompletionRequest, ChatCompletionResponse } from './types';

// You might want to make this configurable via UI
const API_KEY = localStorage.getItem('api_key') || 'han1234';

const client = axios.create({
  baseURL: '',
  headers: {
    'Authorization': `Bearer ${API_KEY}`,
    'Content-Type': 'application/json',
  },
});

// Interceptor to update token if it changes in localStorage
client.interceptors.request.use((config) => {
  const token = localStorage.getItem('api_key') || 'han1234';
  config.headers.Authorization = `Bearer ${token}`;
  return config;
});

export const getAccounts = async () => {
  const response = await client.get<{ data: Account[] }>('/v1/accounts');
  return response.data.data;
};

export const getModels = async () => {
  const response = await client.get<{ data: Model[] }>('/v1/models');
  return response.data.data;
};

export const createChatCompletion = async (data: ChatCompletionRequest) => {
  const response = await client.post<ChatCompletionResponse>('/v1/chat/completions', data);
  return response.data;
};

export const streamChatCompletion = async (
  data: ChatCompletionRequest,
  onChunk: (chunk: ChatCompletionResponse) => void,
  onError: (error: any) => void,
  onFinish: () => void
) => {
  try {
    const response = await fetch('/v1/chat/completions', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${localStorage.getItem('api_key') || 'han1234'}`,
      },
      body: JSON.stringify({ ...data, stream: true }),
    });

    if (!response.ok) {
      const errorText = await response.text();
      throw new Error(`API Error: ${response.status} - ${errorText}`);
    }

    const reader = response.body?.getReader();
    const decoder = new TextDecoder();

    if (!reader) throw new Error('No reader available');

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      const chunk = decoder.decode(value);
      const lines = chunk.split('\n');

      for (const line of lines) {
        if (line.startsWith('data: ')) {
          const dataStr = line.slice(6);
          if (dataStr === '[DONE]') {
            onFinish();
            return;
          }
          try {
            const parsed = JSON.parse(dataStr);
            onChunk(parsed);
          } catch (e) {
            console.error('Error parsing chunk', e);
          }
        }
      }
    }
  } catch (error) {
    onError(error);
  }
};
