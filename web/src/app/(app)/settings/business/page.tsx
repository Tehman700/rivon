import type { Metadata } from "next"

import { PageHeader, ReadOnlyNotice } from "@/components/page-header"
import { getMe, getProfile } from "@/lib/api/server"

import { BusinessProfileForm } from "./business-profile-form"

export const metadata: Metadata = { title: "Business profile" }

export default async function BusinessProfilePage() {
  const [me, profile] = await Promise.all([getMe(), getProfile()])
  const canEdit = me.role === "owner"
  return (
    <>
      <PageHeader
        title="Business profile"
        description="The basics Rivon uses in conversations and on quotations."
      />
      {!canEdit && <ReadOnlyNotice />}
      <BusinessProfileForm profile={profile} canEdit={canEdit} />
    </>
  )
}
