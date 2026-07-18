"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import type { ApiError } from "@/core/api/apiClient";
import { chatApi } from "@/features/chat/data/chatApi";

export function useChatList() {
  return useQuery({
    queryKey: ["chats"],
    queryFn: chatApi.listChats,
    staleTime: 60 * 1000,
  });
}

export function useChatHistory(chatId: string | null) {
  return useQuery({
    queryKey: ["chats", chatId, "messages"],
    queryFn: () => chatApi.getHistory(chatId as string),
    enabled: Boolean(chatId),
  });
}

export function useSendMessage() {
  const queryClient = useQueryClient();

  return useMutation<
    { chatId: string; reply: string },
    ApiError,
    { message: string; chatId: string | null }
  >({
    mutationFn: ({ message, chatId }) => chatApi.sendMessage(message, chatId ?? undefined),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ["chats"] });
      if (variables.chatId) {
        queryClient.invalidateQueries({ queryKey: ["chats", variables.chatId, "messages"] });
      }
    },
  });
}
