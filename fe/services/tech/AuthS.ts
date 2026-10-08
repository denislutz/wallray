import { SignJWT } from "jose";
import NextAuth from "next-auth";
import Credentials from "next-auth/providers/credentials";
// import Google from "next-auth/providers/google";
// import Twitter from "next-auth/providers/twitter";
import { type SignInResponse, signIn, signOut, useSession } from "next-auth/react";

import EnvS from "@/services/tech/EnvS";
import RoutingS from "@/services/tech/RoutingS";
import type { OtpUser } from "@/types/api";
import type { Session } from "next-auth";

declare module "next-auth" {
  interface Session {
    apiToken: string;
  }
}

// ============================================================================
// Private
// ============================================================================

const DEV_USER = {
  id: "502525d7-90d7-4c42-ab44-bab254cfa3a5",
  name: "Dev User",
  email: "owner@example.com",
};

const devProvider =
  process.env.NEXT_PUBLIC_DEV_AUTH === "true"
    ? [Credentials({ id: "dev", authorize: () => DEV_USER })]
    : [];

const credentialsProvider = Credentials({
  id: "credentials",
  credentials: { email: {}, code: {} },
  authorize: async (creds) => {
    const email = String(creds.email ?? "");
    const code = String(creds.code ?? "");
    if (!email || !code) return null;
    try {
      const apiUrl = process.env.BE_BASE_URL ?? process.env.NEXT_PUBLIC_BE_BASE_URL;
      if (!apiUrl) throw new Error("BE_BASE_URL is not set");
      const res = await fetch(`${apiUrl}/auth/otp/verify`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, code }),
      });
      if (!res.ok) return null;
      const user = (await res.json()) as OtpUser;
      return { id: user.id, email: user.email, name: user.name ?? null };
    } catch {
      return null;
    }
  },
});

const { handlers, auth } = NextAuth({
  providers: [credentialsProvider, ...devProvider],
  // providers: [Google, Twitter, credentialsProvider, ...devProvider],
  session: { strategy: "jwt" },
  pages: { signIn: RoutingS.paths.signIn() },
  callbacks: {
    jwt({ token }) {
      return token;
    },
    async session({ session, token }) {
      const rawSecret = process.env.AUTH_SECRET ?? "";
      const secret = new TextEncoder().encode(rawSecret);
      session.apiToken = await new SignJWT({
        sub: token.sub,
        email: token.email,
      })
        .setProtectedHeader({ alg: "HS256" })
        .setIssuedAt()
        .setExpirationTime("7d")
        .sign(secret);
      return session;
    },
  },
});

const getToken = (session: Session | null): string | null => session?.apiToken ?? null;

const sendOtp = async (
  email: string,
  termsAccepted: boolean,
  turnstileToken: string
): Promise<void> => {
  const res = await fetch(`${EnvS.apiUrl()}/auth/otp/send`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      email,
      terms_accepted: termsAccepted,
      turnstile_token: turnstileToken,
    }),
  });
  // A captcha/rate-limit rejection must surface as an error — otherwise the caller shows
  // "check your inbox" for a request the backend silently dropped.
  if (!res.ok) throw new Error(`otp/send failed: ${res.status}`);
};

const signInWithOtp = (email: string, code: string): Promise<SignInResponse> =>
  signIn("credentials", { email, code, redirect: false }) as Promise<SignInResponse>;

const isValidEmail = (email: string): boolean => /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(email.trim());

// ============================================================================
// Public service API
// ============================================================================

const useAuth = () => {
  const { data: session } = useSession();
  return {
    user: session?.user ?? null,
    token: getToken(session),
    signIn: () => void signIn(),
    signInDev: EnvS.devAuth()
      ? () => void signIn("dev", { redirectTo: RoutingS.paths.reports() })
      : null,
    signOut: () => void signOut(),
  };
};

const AuthS = { handlers, auth, useAuth, sendOtp, signInWithOtp, isValidEmail };
export default AuthS;
