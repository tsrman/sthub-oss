import { useParams } from 'next/navigation';

/** Return the current streamlit route id as a single path segment. */
export function useStreamlitId(): string {
  const { id } = useParams<{ id?: string | string[] }>();
  return Array.isArray(id) ? (id[0] ?? '') : (id ?? '');
}
