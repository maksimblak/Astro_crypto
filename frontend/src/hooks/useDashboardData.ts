import { useQuery } from '@tanstack/react-query';
import { api } from '../api/client';

const STALE = 5 * 60 * 1000;

export function useToday() {
  return useQuery({ queryKey: ['today'], queryFn: api.today, staleTime: STALE });
}

export function useCalendar() {
  return useQuery({ queryKey: ['calendar'], queryFn: api.calendar, staleTime: STALE });
}

export function useDaily() {
  return useQuery({ queryKey: ['daily'], queryFn: api.daily, staleTime: STALE });
}

export function usePivots() {
  return useQuery({ queryKey: ['pivots'], queryFn: api.pivots, staleTime: STALE });
}

export function useStats() {
  return useQuery({ queryKey: ['stats'], queryFn: api.stats, staleTime: STALE });
}

export function useRegime() {
  return useQuery({ queryKey: ['regime'], queryFn: api.regime, staleTime: STALE });
}

export function useCycle() {
  return useQuery({ queryKey: ['cycle'], queryFn: api.cycle, staleTime: STALE });
}
