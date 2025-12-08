export interface Account {
  email: string;
  is_active: boolean;
  plan_type: string | null;
  plan_title: string | null;
  subscription_end: string | null;
  sora2_remaining_count: number;
  sora2_total_count: number;
  image_count: number;
  video_count: number;
}

export interface Model {
  id: string;
  object: string;
  owned_by: string;
  description: string;
}

export interface ChatMessage {
  role: string;
  content: string;
}

export interface ChatCompletionRequest {
  model: string;
  messages: ChatMessage[];
  stream?: boolean;
  image?: string; // base64
  video?: string; // base64 or url
  remix_target_id?: string;
  email?: string;
}

export interface ChatCompletionResponse {
  id: string;
  object: string;
  created: number;
  model: string;
  choices: {
    index: number;
    message?: ChatMessage;
    delta?: { role?: string; content?: string | null; reasoning_content?: string | null };
    finish_reason: string | null;
  }[];
}
