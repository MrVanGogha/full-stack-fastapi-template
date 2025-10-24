import { Container, Image, Input, Text } from "@chakra-ui/react"
import {
  createFileRoute,
  Link as RouterLink,
  redirect,
} from "@tanstack/react-router"
import { type SubmitHandler, useForm } from "react-hook-form"
import { FiLock, FiMail, FiPhone, FiHash } from "react-icons/fi"
import { useState } from "react"

import type { Body_login_login_access_token as AccessToken } from "@/client"
import { Button } from "@/components/ui/button"
import { Field } from "@/components/ui/field"
import { InputGroup } from "@/components/ui/input-group"
import { PasswordInput } from "@/components/ui/password-input"
import useAuth, { isLoggedIn } from "@/hooks/useAuth"
import Logo from "/assets/images/fastapi-logo.svg"
import { emailPattern, passwordRules } from "../utils"
import { useMutation } from "@tanstack/react-query"
import useCustomToast from "@/hooks/useCustomToast"
import { OpenAPI } from "@/client"

export const Route = createFileRoute("/login")({
  component: Login,
  beforeLoad: async () => {
    if (isLoggedIn()) {
      throw redirect({
        to: "/",
      })
    }
  },
})

function Login() {
  const { loginMutation, loginByPhoneMutation, error, resetError } = useAuth()
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<AccessToken>({
    mode: "onBlur",
    criteriaMode: "all",
    defaultValues: {
      username: "",
      password: "",
    },
  })
  
  // 手机号验证码登录表单
  interface PhoneLoginRequest {
    phone_number: string
    code: string
  }
  const {
    register: registerPhone,
    handleSubmit: handlePhoneSubmit,
    getValues: getPhoneValues,
    formState: { errors: errorsPhone, isSubmitting: isSubmittingPhone },
  } = useForm<PhoneLoginRequest>({
    mode: "onBlur",
    criteriaMode: "all",
    defaultValues: {
      phone_number: "",
      code: "",
    },
  })
  const [method, setMethod] = useState<"email" | "phone">("email")
  const { showSuccessToast, showErrorToast } = useCustomToast()

  // 发送验证码
  const sendCode = async () => {
    const phone = getPhoneValues("phone_number")
    if (!phone) {
      showErrorToast("请输入手机号")
      return
    }
    const response = await fetch(`${OpenAPI.BASE}/api/v1/auth/phone/send-code`, {
      method: "POST",
      credentials: "include",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ phone_number: phone }),
    })
    if (!response.ok) {
      const text = await response.text()
      throw new Error(text || "发送验证码失败")
    }
    try {
      const obj = await response.json()
      if (obj?.code) {
        showSuccessToast(`验证码已发送：${obj.code}`)
      } else {
        showSuccessToast("验证码已发送")
      }
    } catch {
      showSuccessToast("验证码已发送")
    }
  }
  const sendCodeMutation = useMutation({
    mutationFn: sendCode,
    onError: (err: any) => {
      showErrorToast(err?.message ?? "发送验证码失败")
    },
  })

  const onSubmit: SubmitHandler<AccessToken> = async (data) => {
    if (isSubmitting) return

    resetError()

    try {
      await loginMutation.mutateAsync(data)
    } catch {
      // error is handled by useAuth hook
    }
  }

  // 手机号登录提交
  const onPhoneSubmit: SubmitHandler<PhoneLoginRequest> = async (data) => {
    if (isSubmittingPhone) return

    resetError()

    try {
      await loginByPhoneMutation.mutateAsync(data)
    } catch {
      // error is handled by useAuth hook / toast
    }
  }

  return (
    <Container
      as="form"
      onSubmit={method === "email" ? handleSubmit(onSubmit) : handlePhoneSubmit(onPhoneSubmit)}
      h="100vh"
      maxW="sm"
      alignItems="stretch"
      justifyContent="center"
      gap={4}
      centerContent
    >
      <Image
        src={Logo}
        alt="FastAPI logo"
        height="auto"
        maxW="2xs"
        alignSelf="center"
        mb={4}
      />
      <Text>
        {method === "email" ? (
          <>
            使用手机号验证码登录？{" "}
            <button type="button" className="main-link" onClick={() => setMethod("phone")}>
              手机号登录
            </button>
          </>
        ) : (
          <>
            使用邮箱密码登录？{" "}
            <button type="button" className="main-link" onClick={() => setMethod("email")}>
              邮箱登录
            </button>
          </>
        )}
      </Text>
      {method === "email" && (
        <>
          <Field
            invalid={!!errors.username}
            errorText={errors.username?.message || !!error}
          >
            <InputGroup w="100%" startElement={<FiMail />}>
              <Input
                {...register("username", {
                  required: "Username is required",
                  pattern: emailPattern,
                })}
                placeholder="Email"
                type="email"
              />
            </InputGroup>
          </Field>
          <PasswordInput
            type="password"
            startElement={<FiLock />}
            {...register("password", passwordRules())}
            placeholder="Password"
            errors={errors}
          />
          <RouterLink to="/recover-password" className="main-link">
            Forgot Password?
          </RouterLink>
          <Button variant="solid" type="submit" loading={isSubmitting} size="md">
            Log In
          </Button>
          <Button
            variant="outline"
            type="button"
            onClick={() => {
              window.location.href = `${OpenAPI.BASE}/api/v1/auth/wechat/authorize`
            }}
          >
            微信扫码登录
          </Button>
          <Text>
            Don't have an account?{" "}
            <RouterLink to="/signup" className="main-link">
              Sign Up
            </RouterLink>
          </Text>
        </>
      )}
      {method === "phone" && (
        <>
          <Field
            invalid={!!errorsPhone.phone_number}
            errorText={errorsPhone.phone_number?.message || !!error}
          >
            <InputGroup w="100%" startElement={<FiPhone />}>
              <Input
                {...registerPhone("phone_number", {
                  required: "手机号不能为空",
                })}
                placeholder="手机号"
                type="tel"
              />
            </InputGroup>
          </Field>
          <Field
            invalid={!!errorsPhone.code}
            errorText={errorsPhone.code?.message || !!error}
          >
            <InputGroup w="100%" startElement={<FiHash />}>
              <Input
                {...registerPhone("code", {
                  required: "验证码不能为空",
                })}
                placeholder="验证码"
                type="text"
              />
            </InputGroup>
          </Field>
          <Button
            variant="outline"
            type="button"
            loading={sendCodeMutation.isPending}
            onClick={() => sendCodeMutation.mutate()}
          >
            发送验证码
          </Button>
          <Button variant="solid" type="submit" loading={isSubmittingPhone} size="md">
            手机号登录
          </Button>
        </>
      )}
    </Container>
  )
}
