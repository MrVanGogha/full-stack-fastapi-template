import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { useNavigate } from "@tanstack/react-router"
import { useState } from "react"

import {
  type Body_auth_login_access_token as AccessToken,
  type ApiError,
  AuthService,
  type UserPublic,
  type UserRegister,
  UsersService,
} from "@/client"
import { handleError } from "@/utils"
import { OpenAPI } from "@/client"

const isLoggedIn = () => {
  return localStorage.getItem("access_token") !== null
}

const useAuth = () => {
  const [error, setError] = useState<string | null>(null)
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { data: user } = useQuery<UserPublic | null, Error>({
    queryKey: ["currentUser"],
    queryFn: UsersService.readUserMe,
    enabled: isLoggedIn(),
  })

  const signUpMutation = useMutation({
    mutationFn: (data: UserRegister) =>
      UsersService.registerUser({ requestBody: data }),

    onSuccess: () => {
      navigate({ to: "/login" })
    },
    onError: (err: ApiError) => {
      handleError(err)
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ["users"] })
    },
  })

  const login = async (data: AccessToken) => {
    const response = await AuthService.loginAccessToken({
      formData: data,
    })
    localStorage.setItem("access_token", response.access_token)
  }

  const loginMutation = useMutation({
    mutationFn: login,
    onSuccess: () => {
      navigate({ to: "/" })
    },
    onError: (err: ApiError) => {
      handleError(err)
    },
  })

  // 手机号验证码登录
  const loginByPhone = async (data: { phone_number: string; code: string }) => {
    const res = await fetch(`${OpenAPI.BASE}/api/v1/auth/phone/login`, {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    })
    if (!res.ok) {
      let message = "Phone login failed"
      try {
        const body = await res.json()
        const detail = (body as any)?.detail
        if (detail) {
          message = Array.isArray(detail) && detail.length > 0 ? detail[0].msg : detail
        }
      } catch {
        try {
          message = await res.text()
        } catch {}
      }
      throw new Error(message)
    }
    const token = await res.json()
    localStorage.setItem("access_token", token.access_token)
  }

  const loginByPhoneMutation = useMutation({
    mutationFn: loginByPhone,
    onSuccess: () => {
      navigate({ to: "/" })
    },
    onError: (err: any) => {
      handleError(err as any)
    },
  })

  const logout = async () => {
    try {
      await fetch(`${OpenAPI.BASE}/api/v1/auth/logout`, {
        method: "POST",
        credentials: "include",
        headers: {
          Authorization: `Bearer ${localStorage.getItem("access_token") || ""}`,
        },
      })
    } catch (e) {
      // ignore
    }
    localStorage.removeItem("access_token")
    navigate({ to: "/login" })
  }

  return {
    signUpMutation,
    loginMutation,
    loginByPhoneMutation,
    logout,
    user,
    error,
    resetError: () => setError(null),
  }
}

export { isLoggedIn }
export default useAuth
