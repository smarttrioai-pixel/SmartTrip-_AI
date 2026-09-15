import React, { useRef } from 'react';
import { Plus, Image as ImageIcon } from 'lucide-react';
import type { DiaryPhoto } from '../domain/types';

interface DiaryPhotoGridProps {
  photos: DiaryPhoto[];
  onAdd: (file: File) => void;
  isLoading?: boolean;
}

export function DiaryPhotoGrid({ photos, onAdd, isLoading }: DiaryPhotoGridProps) {
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      onAdd(file);
    }
    // reset input so same file can be selected again if needed
    if (e.target) {
      e.target.value = '';
    }
  };

  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
      {photos.map((photo, index) => (
        <div key={index} className="relative aspect-square rounded-xl overflow-hidden bg-ink-100 dark:bg-ink-800 border border-ink-200 dark:border-ink-700 group">
          {photo.url ? (
            <img src={photo.url} alt={photo.gemini_description || 'Diary photo'} className="w-full h-full object-cover" />
          ) : photo.image_b64 ? (
            <img src={`data:image/jpeg;base64,${photo.image_b64}`} alt="Diary photo" className="w-full h-full object-cover" />
          ) : (
            <div className="w-full h-full flex flex-col items-center justify-center p-2 text-center text-ink-400">
              <ImageIcon className="h-6 w-6 mb-2 opacity-50" />
              <span className="text-[10px] line-clamp-3">{photo.gemini_description || 'Photo processing...'}</span>
            </div>
          )}
        </div>
      ))}

      {isLoading ? (
        <div className="aspect-square rounded-xl bg-ink-100 dark:bg-ink-800 border border-ink-200 dark:border-ink-700 animate-pulse flex items-center justify-center">
          <span className="text-sm text-ink-400">Uploading...</span>
        </div>
      ) : (
        <button
          onClick={() => fileInputRef.current?.click()}
          className="aspect-square rounded-xl border-2 border-dashed border-ink-200 dark:border-ink-700 hover:border-brand-500 hover:bg-brand-50 dark:hover:bg-brand-900/20 transition-colors flex flex-col items-center justify-center gap-2 text-ink-500 hover:text-brand-600 dark:hover:text-brand-400"
        >
          <Plus className="h-6 w-6" />
          <span className="text-xs font-medium">Add Photo</span>
        </button>
      )}

      <input
        type="file"
        ref={fileInputRef}
        onChange={handleFileChange}
        accept="image/*"
        className="hidden"
      />
    </div>
  );
}
