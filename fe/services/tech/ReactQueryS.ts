import {
  QueryClient,
  QueryClientProvider,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import type {
  UseMutationOptions,
  UseMutationResult,
  UseQueryOptions,
  UseQueryResult,
} from "@tanstack/react-query";

// ============================================================================
// Private
// ============================================================================

const createClient = () =>
  new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        refetchOnWindowFocus: false,
        staleTime: 0,
      },
    },
  });

// ============================================================================
// Public service API
// ============================================================================

export type { UseMutationOptions, UseMutationResult, UseQueryOptions, UseQueryResult };

const ReactQueryS = {
  createClient,
  Provider: QueryClientProvider,
  useQuery,
  useMutation,
  useQueryClient,
};

export default ReactQueryS;
