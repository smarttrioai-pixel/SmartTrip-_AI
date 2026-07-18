import { apiClient } from "@/core/api/apiClient";
import type { ChatMessage, ChatSummary } from "@/features/chat/domain/types";

interface SendMessageResponseDto {
  chat_id: string;
  reply: string;
}

export const chatApi = {
  async sendMessage(message: string, chatId?: string): Promise<{ chatId: string; reply: string }> {
    const { data } = await apiClient.post<SendMessageResponseDto>("/chat/messages", {
      message,
      chat_id: chatId ?? null,
    });
    return { chatId: data.chat_id, reply: data.reply };
  },

  async getHistory(chatId: string): Promise<ChatMessage[]> {
    const { data } = await apiClient.get<ChatMessage[]>(`/chat/${chatId}/messages`);
    return data;
  },

  async listChats(): Promise<ChatSummary[]> {
    const { data } = await apiClient.get<ChatSummary[]>("/chat");
    return data;
  },
};
