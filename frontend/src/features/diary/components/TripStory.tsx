import React from 'react';
import { BookOpen, Sparkles } from 'lucide-react';
import type { TripStory as TripStoryType } from '../domain/types';
import { Button } from '@/shared/components/ui/button';

interface TripStoryProps {
  tripId: string;
  story: TripStoryType | null;
  onGenerate: () => void;
  isGenerating?: boolean;
}

export function TripStory({ tripId, story, onGenerate, isGenerating }: TripStoryProps) {
  return (
    <div className="bg-gradient-to-br from-brand-600 to-indigo-700 text-white p-1 rounded-2xl shadow-lg mt-8">
      <div className="bg-ink-900/10 backdrop-blur-sm rounded-xl p-6 md:p-8">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 mb-6 border-b border-white/20 pb-4">
          <div className="flex items-center gap-3">
            <div className="bg-white/20 p-2.5 rounded-xl">
              <BookOpen className="h-6 w-6 text-white" />
            </div>
            <div>
              <h2 className="text-xl font-bold font-display">The Complete Trip Story</h2>
              <p className="text-sm text-brand-100 opacity-90">A generated narrative of your entire journey</p>
            </div>
          </div>
          
          {story && (
            <Button 
              variant="outline" 
              onClick={onGenerate} 
              disabled={isGenerating}
              className="bg-white/10 hover:bg-white/20 border-white/30 text-white"
            >
              <Sparkles className="h-4 w-4 mr-2" />
              {isGenerating ? 'Regenerating...' : 'Regenerate Story'}
            </Button>
          )}
        </div>

        {story ? (
          <div className="prose prose-invert prose-brand max-w-none text-brand-50 leading-loose">
            <div className="whitespace-pre-wrap text-base md:text-lg">{story.content}</div>
          </div>
        ) : (
          <div className="flex flex-col items-center justify-center text-center py-10 px-4">
            <div className="bg-white/10 w-16 h-16 rounded-full flex items-center justify-center mb-4">
              <Sparkles className="h-8 w-8 text-brand-200" />
            </div>
            <h3 className="text-xl font-bold mb-2">No Story Yet</h3>
            <p className="text-brand-100 max-w-md mx-auto mb-6 opacity-90">
              Generate a comprehensive, beautifully written narrative summarizing your entire trip based on all your diary entries.
            </p>
            <Button 
              onClick={onGenerate} 
              disabled={isGenerating}
              className="bg-white text-brand-700 hover:bg-brand-50 border-none font-semibold px-8 py-6 h-auto text-base shadow-xl"
            >
              <Sparkles className="h-5 w-5 mr-2" />
              {isGenerating ? 'Weaving your story...' : 'Generate My Trip Story'}
            </Button>
          </div>
        )}
      </div>
    </div>
  );
}
