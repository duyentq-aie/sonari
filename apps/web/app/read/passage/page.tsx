import PassageView from "./view";

export default async function Page({ searchParams }: { searchParams: Promise<{ id?: string }> }) {
  const { id } = await searchParams;
  return <PassageView id={typeof id === "string" ? id : ""} />;
}
