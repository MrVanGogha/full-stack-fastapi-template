import { createFileRoute, useNavigate } from "@tanstack/react-router"
import { useEffect } from "react"

export const Route = createFileRoute("/login-success")({
  component: LoginSuccess,
})

function LoginSuccess() {
  const navigate = useNavigate()
  useEffect(() => {
    try {
      const url = new URL(window.location.href)
      const token = url.searchParams.get("access_token")
      if (token) {
        localStorage.setItem("access_token", token)
        navigate({ to: "/" })
      } else {
        navigate({ to: "/login" })
      }
    } catch {
      navigate({ to: "/login" })
    }
  }, [navigate])
  return null
}