import HttpS from "@/services/tech/HttpS";
import ReactQueryS from "@/services/tech/ReactQueryS";

// ============================================================================
// Private
// ============================================================================

interface MeResponse {
  role: string;
  email: string;
  preferred_language: string;
}

const getMe = (token: string): Promise<MeResponse> => HttpS.get<MeResponse>("/me", token);

const patchLanguage = (token: string, language: string): Promise<void> =>
  HttpS.patch<void>("/me/language", { language }, token);

// ============================================================================
// Public service API
// ============================================================================

const useMe = (token: string | null): { me: MeResponse | null } => {
  const { data } = ReactQueryS.useQuery({
    queryKey: ["me"],
    queryFn: () => getMe(token ?? ""),
    enabled: !!token,
  });
  return { me: data ?? null };
};

const useUpdateLanguage = (token: string | null) => {
  const queryClient = ReactQueryS.useQueryClient();
  return ReactQueryS.useMutation({
    mutationFn: (language: string) => patchLanguage(token ?? "", language),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["me"] });
    },
  });
};

const AccountS = { useMe, useUpdateLanguage };
export default AccountS;
