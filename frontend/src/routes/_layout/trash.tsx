import { Container, Flex, Heading, Table, VStack, EmptyState, Text, Button } from "@chakra-ui/react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { createFileRoute, useNavigate } from "@tanstack/react-router"
import { FiTrash, FiRotateCcw, FiTrash2 } from "react-icons/fi"
import useCustomToast from "@/hooks/useCustomToast"
import {
  DialogActionTrigger,
  DialogBody,
  DialogCloseTrigger,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogRoot,
  DialogTrigger,
  DialogTitle,
} from "@/components/ui/dialog"
import { useState } from "react"
import { ItemsService } from "@/client"
import type { ItemsReadTrashItemsResponse, ItemTrashPublic } from "@/client/types.gen"

const PER_PAGE = 5


function getTrashQueryOptions({ page }: { page: number }) {
  return {
    queryFn: async (): Promise<ItemsReadTrashItemsResponse> => {
      const resp = await ItemsService.readTrashItems({ skip: (page - 1) * PER_PAGE, limit: PER_PAGE })
      return resp
    },
    queryKey: ["items-trash", { page }],
  }
}

export const Route = createFileRoute("/_layout/trash")({
  component: TrashPage,
})

function formatRemaining(expires_at?: string | Date | null) {
  if (!expires_at) return "暂无"
  const exp = new Date(expires_at)
  const now = new Date()
  const ms = exp.getTime() - now.getTime()
  if (ms <= 0) return "已过期"
  const days = Math.floor(ms / (24 * 3600 * 1000))
  const hours = Math.floor((ms % (24 * 3600 * 1000)) / (3600 * 1000))
  return `${days}d ${hours}h`
}

function TrashTable() {
  const page = 1 // minimal: single page for now
  const queryClient = useQueryClient()
  const { showSuccessToast, showErrorToast } = useCustomToast()

  const { data, isLoading } = useQuery<ItemsReadTrashItemsResponse>({
    ...getTrashQueryOptions({ page }),
    placeholderData: (prevData) => prevData,
  })

  const items = data?.data ?? []
  const count = data?.count ?? 0

  const [purgeId, setPurgeId] = useState<string | null>(null)
  const [restoreId, setRestoreId] = useState<string | null>(null)

  const restoreMutation = useMutation({
    mutationFn: async (id: string) => {
      return ItemsService.restoreItem({ id })
    },
    onSuccess: () => {
      showSuccessToast("项目已成功恢复")
      setRestoreId(null)
    },
    onError: () => {
      showErrorToast("恢复项目时发生错误")
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ["items-trash"] })
    },
  })

  const purgeMutation = useMutation({
    mutationFn: async (id: string) => {
      return ItemsService.purgeItem({ id })
    },
    onSuccess: () => {
      showSuccessToast("项目已被永久删除")
      setPurgeId(null)
    },
    onError: () => {
      showErrorToast("删除项目时发生错误")
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ["items-trash"] })
    },
  })

  if (isLoading) {
    return <Text>加载中...</Text>
  }

  if (items.length === 0) {
    return (
      <EmptyState.Root>
        <EmptyState.Content>
          <EmptyState.Indicator>
            <FiTrash />
          </EmptyState.Indicator>
          <VStack textAlign="center">
            <EmptyState.Title>回收站为空</EmptyState.Title>
            <EmptyState.Description>软删除的项目会显示在这里，支持恢复或永久删除</EmptyState.Description>
          </VStack>
        </EmptyState.Content>
      </EmptyState.Root>
    )
  }

  return (
    <>
      <Table.Root size={{ base: "sm", md: "md" }}>
        <Table.Header>
          <Table.Row>
            <Table.ColumnHeader w="sm">编号</Table.ColumnHeader>
            <Table.ColumnHeader w="sm">标题</Table.ColumnHeader>
            <Table.ColumnHeader w="sm">删除时间</Table.ColumnHeader>
            <Table.ColumnHeader w="sm">有效期至</Table.ColumnHeader>
            <Table.ColumnHeader w="sm">操作</Table.ColumnHeader>
          </Table.Row>
        </Table.Header>
        <Table.Body>
          {items.map((item: ItemTrashPublic) => (
            <Table.Row key={item.id}>
              <Table.Cell truncate maxW="sm">{item.id}</Table.Cell>
              <Table.Cell truncate maxW="sm">{item.title}</Table.Cell>
              <Table.Cell truncate maxW="sm">{new Date(item.deleted_at).toLocaleString()}</Table.Cell>
              <Table.Cell truncate maxW="sm">{formatRemaining(item.expires_at)}</Table.Cell>
              <Table.Cell>
                <Flex gap={2} wrap="wrap">
                  {/* Restore */}
                  <DialogRoot
                    size={{ base: "xs", md: "md" }}
                    placement="center"
                    role="alertdialog"
                    open={restoreId === item.id}
                    onOpenChange={({ open }) => setRestoreId(open ? item.id : null)}
                  >
                    <DialogTrigger asChild>
                      <Button variant="solid" size="sm" colorPalette="green">
                        <FiRotateCcw fontSize="16px" />
                        恢复
                      </Button>
                    </DialogTrigger>
                    <DialogContent>
                      <DialogCloseTrigger />
                      <DialogHeader>
                        <DialogTitle>恢复项目</DialogTitle>
                      </DialogHeader>
                      <DialogBody>
                        <Text mb={4}>
                          该项目将从回收站中恢复，是否继续？
                        </Text>
                      </DialogBody>
                      <DialogFooter gap={2}>
                        <DialogActionTrigger asChild>
                          <Button variant="subtle" colorPalette="gray">取消</Button>
                        </DialogActionTrigger>
                        <Button
                          variant="solid"
                          colorPalette="green"
                          onClick={() => restoreMutation.mutate(item.id)}
                          loading={restoreMutation.isPending}
                        >
                          恢复
                        </Button>
                      </DialogFooter>
                    </DialogContent>
                  </DialogRoot>

                  {/* Purge */}
                  <DialogRoot
                    size={{ base: "xs", md: "md" }}
                    placement="center"
                    role="alertdialog"
                    open={purgeId === item.id}
                    onOpenChange={({ open }) => setPurgeId(open ? item.id : null)}
                  >
                    <DialogTrigger asChild>
                      <Button variant="ghost" size="sm" colorPalette="red">
                        <FiTrash2 fontSize="16px" />
                        永久删除
                      </Button>
                    </DialogTrigger>

                    <DialogContent>
                      <DialogCloseTrigger />
                      <DialogHeader>
                        <DialogTitle>永久删除项目</DialogTitle>
                      </DialogHeader>
                      <DialogBody>
                        <Text mb={4}>
                          该项目将被永久删除，操作不可撤销。是否继续？
                        </Text>
                      </DialogBody>
                      <DialogFooter gap={2}>
                        <DialogActionTrigger asChild>
                          <Button variant="subtle" colorPalette="gray">取消</Button>
                        </DialogActionTrigger>
                        <Button
                          variant="solid"
                          colorPalette="red"
                          onClick={() => purgeMutation.mutate(item.id)}
                          loading={purgeMutation.isPending}
                        >
                          永久删除
                        </Button>
                      </DialogFooter>
                    </DialogContent>
                  </DialogRoot>
                </Flex>
              </Table.Cell>
            </Table.Row>
          ))}
        </Table.Body>
      </Table.Root>
    </>
  )
}

function TrashPage() {
  const navigate = useNavigate()

  return (
    <Container maxW="container.lg" py={{ base: "6", md: "12" }}>
      <Heading size={{ base: "md", md: "lg" }}>回收站</Heading>

      <Text color="fg.cta" mt="2" mb="6">
        已软删除的项目显示在这里，可恢复或永久删除。默认保留 7 天。
      </Text>

      <TrashTable />
    </Container>
  )
}

export default TrashPage