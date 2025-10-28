import { Container, Heading, Text } from "@chakra-ui/react"

import DeleteConfirmation from "./DeleteConfirmation"

const DeleteAccount = () => {
  return (
    <Container maxW="full">
      <Heading size="sm" py={4}>
        删除账户
      </Heading>
      <Text>
        将永久删除您的数据及与账户相关的所有信息。
      </Text>
      <DeleteConfirmation />
    </Container>
  )
}
export default DeleteAccount
