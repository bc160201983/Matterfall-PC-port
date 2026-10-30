/* System functions added for Matterfall (CUSA02475, Unreal Engine 4.13), offline and
 * single-user like runtime_services.c:
 *   - PSN (NpToolkit2, NpManager, Matching2, Score, Tus/Tss, WebApi, WordFilter): every request
 *     fails at once with "signed out", so the game never waits for a reply;
 *   - Json2: objects are left untouched and serialization fails (only used to build PSN requests);
 *   - USB keyboard IME, content export, live streaming, DLC: absent;
 *   - pthread_detach (POSIX name of scePthreadDetach).
 * Every entry is an explicit contract; unknown functions still stop. */
#include "runtime.h"
#include <stdio.h>
#include <string.h>

#define NP_SIGNED_OUT ((int32_t)0x80550006)
#define NP_TUS_NO_LOGIN ((int32_t)0x80550705)
#define DISC_MAP_NO_BITMAP ((int32_t)0x81100004)
#define APP_CONTENT_NO_ENTITLEMENT ((int32_t)0x80D90007)
#define IME_NOT_CONNECTED ((int32_t)0x80BC0003)
#define GENERIC_UNAVAILABLE ((int32_t)0x80020016)

static size_t np_refusals, json_calls;

static ABI int32_t ok(void) { return 0; }
static ABI void nothing(void) {}
static ABI int32_t signed_out(void) { ++np_refusals; return NP_SIGNED_OUT; }
static ABI int32_t tus_no_login(void) { ++np_refusals; return NP_TUS_NO_LOGIN; }
static ABI int32_t unavailable(void) { return GENERIC_UNAVAILABLE; }
static ABI int32_t no_bitmap(void) { return DISC_MAP_NO_BITMAP; }
static ABI int32_t no_entitlement(void) { return APP_CONTENT_NO_ENTITLEMENT; }
static ABI int32_t no_keyboard(void) { return IME_NOT_CONNECTED; }

/* NpToolkit2 Response<T>::get() and Json2 references: a zeroed object (empty lists, no data).
 * Nothing writes it here; a caller that writes into it only changes this scratch memory. */
static _Alignas(64) unsigned char empty_object[64 * 1024];
static ABI void *empty(void) { return empty_object; }
/* Json2 calls (the game builds PSN request bodies with them): no state is kept. */
static ABI void json_nothing(void) { ++json_calls; }
static ABI void *json_self(void *this_) { ++json_calls; return this_; }
static ABI void *json_empty(void) { ++json_calls; return empty_object; }
static ABI int32_t json_fail(void) { ++json_calls; return GENERIC_UNAVAILABLE; }
static ABI uint64_t json_zero(void) { ++json_calls; return 0; }
static ABI int32_t toolkit_unlocked(void) { return 0; }

/* POSIX pthread_detach: scePthreadDetach with the POSIX error convention. */
typedef int32_t (ABI *DetachFn)(void *);
static ABI int32_t posix_detach(void *thread) {
    DetachFn detach=(DetachFn)runtime_thread_resolve("4qGrR6eoP9Y#libkernel");
    int32_t r=detach ? detach(thread) : GENERIC_UNAVAILABLE;
    return r ? (int32_t)((uint32_t)r & 0xffff) : 0;
}

/* Names of the C++ toolkit and Json2 entry points (Itanium mangling). */
#define TK "_ZN3sce7Toolkit2NP2V2"
#define TKR(type) TK "4Core8ResponseI" type "EE"
static const RuntimeExport exports[]={
    /* NpToolkit2 core: init succeeds (offline toolkit); every request is refused. */
    {TK "4Core4initERKNS3_7Request10InitParamsE",ok},
    {TK "4Core4termERKNS3_7Request10TermParamsE",ok},
    {TK "4Core7Request10InitParamsC1Ev",nothing}, {TK "4Core7Request10InitParamsD1Ev",nothing},
    {TK "4Core7Request10TermParamsC1Ev",nothing}, {TK "4Core7Request10TermParamsD1Ev",nothing},
    {TK "4Core12ResponseBase13getReturnCodeEv",signed_out},
    {TK "4Core12ResponseBase8isLockedEv",toolkit_unlocked},
    {TKR("NS3_5Empty") "C1Ev",nothing}, {TKR("NS3_5Empty") "D1Ev",nothing},
    {TKR("NS2_12NetworkUtils12Notification14NetStateChange") "3getEv",empty},
    {TKR("NS2_7NpUtils12Notification15UserStateChange") "3getEv",empty},
    {TKR("NS2_4Auth8AuthCode") "3getEv",empty},
    {TKR("NS2_4Auth8AuthCode") "C1Ev",nothing}, {TKR("NS2_4Auth8AuthCode") "D1Ev",nothing},
    {TKR("NS2_6Friend7Friends") "3getEv",empty},
    {TKR("NS2_6Friend7Friends") "C1Ev",nothing}, {TKR("NS2_6Friend7Friends") "D1Ev",nothing},
    {TKR("NS2_8Commerce10Categories") "3getEv",empty},
    {TKR("NS2_8Commerce10Categories") "C1Ev",nothing}, {TKR("NS2_8Commerce10Categories") "D1Ev",nothing},
    {TKR("NS2_8Commerce19ServiceEntitlements") "3getEv",empty},
    {TKR("NS2_8Commerce19ServiceEntitlements") "C1Ev",nothing}, {TKR("NS2_8Commerce19ServiceEntitlements") "D1Ev",nothing},
    {TKR("NS2_8Commerce8Products") "3getEv",empty},
    {TKR("NS2_8Commerce8Products") "C1Ev",nothing}, {TKR("NS2_8Commerce8Products") "D1Ev",nothing},
    {TKR("NS2_9Messaging16GameDataMessages") "3getEv",empty},
    {TKR("NS2_9Messaging16GameDataMessages") "C1Ev",nothing}, {TKR("NS2_9Messaging16GameDataMessages") "D1Ev",nothing},
    {TKR("NS2_9Messaging25GameDataMessageAttachment") "3getEv",empty},
    {TKR("NS2_9Messaging25GameDataMessageAttachment") "C1Ev",nothing},
    {TKR("NS2_9Messaging25GameDataMessageAttachment") "D1Ev",nothing},
    {TKR("NS2_11UserProfile10NpProfiles") "3getEv",empty},
    {TKR("NS2_11UserProfile10NpProfiles") "C1Ev",nothing}, {TKR("NS2_11UserProfile10NpProfiles") "D1Ev",nothing},
    {TK "11UserProfile9NpProfileD1Ev",nothing},
    /* Requests: constructors/destructors leave the game's object alone; the call is refused. */
    {TK "4Auth11getAuthCodeERKNS3_7Request11GetAuthCodeEPNS2_4Core8ResponseINS3_8AuthCodeEEE",signed_out},
    {TK "4Auth7Request11GetAuthCodeC1Ev",nothing}, {TK "4Auth7Request11GetAuthCodeD1Ev",nothing},
    {TK "6Friend10getFriendsERKNS3_7Request10GetFriendsEPNS2_4Core8ResponseINS3_7FriendsEEE",signed_out},
    {TK "6Friend7Request10GetFriendsC1Ev",nothing}, {TK "6Friend7Request10GetFriendsD1Ev",nothing},
    {TK "7NpUtils24setTitleIdForDevelopmentERKNS3_7Request24SetTitleIdForDevelopmentEPNS2_4Core8ResponseINS8_5EmptyEEE",ok},
    {TK "7NpUtils7Request24SetTitleIdForDevelopmentC1Ev",nothing},
    {TK "7NpUtils7Request24SetTitleIdForDevelopmentD1Ev",nothing},
    {TK "7Session14sendInvitationERKNS3_7Request14SendInvitationEPNS2_4Core8ResponseINS8_5EmptyEEE",signed_out},
    {TK "7Session7Request14SendInvitationC1Ev",nothing}, {TK "7Session7Request14SendInvitationD1Ev",nothing},
    {TK "8Commerce11getProductsERKNS3_7Request11GetProductsEPNS2_4Core8ResponseINS3_8ProductsEEE",signed_out},
    {TK "8Commerce13getCategoriesERKNS3_7Request13GetCategoriesEPNS2_4Core8ResponseINS3_10CategoriesEEE",signed_out},
    {TK "8Commerce21displayCheckoutDialogERKNS3_7Request21DisplayCheckoutDialogEPNS2_4Core8ResponseINS8_5EmptyEEE",signed_out},
    {TK "8Commerce22getServiceEntitlementsERKNS3_7Request22GetServiceEntitlementsEPNS2_4Core8ResponseINS3_19ServiceEntitlementsEEE",signed_out},
    {TK "8Commerce29displayVoucherCodeInputDialogERKNS3_7Request29DisplayVoucherCodeInputDialogEPNS2_4Core8ResponseINS8_5EmptyEEE",signed_out},
    {TK "8Commerce7Request11GetProductsC1Ev",nothing}, {TK "8Commerce7Request11GetProductsD1Ev",nothing},
    {TK "8Commerce7Request13GetCategoriesC1Ev",nothing}, {TK "8Commerce7Request13GetCategoriesD1Ev",nothing},
    {TK "8Commerce7Request21DisplayCheckoutDialogC1Ev",nothing}, {TK "8Commerce7Request21DisplayCheckoutDialogD1Ev",nothing},
    {TK "8Commerce7Request22GetServiceEntitlementsC1Ev",nothing}, {TK "8Commerce7Request22GetServiceEntitlementsD1Ev",nothing},
    {TK "8Commerce7Request29DisplayVoucherCodeInputDialogC1Ev",nothing},
    {TK "8Commerce7Request29DisplayVoucherCodeInputDialogD1Ev",nothing},
    {TK "9Messaging19sendGameDataMessageERKNS3_7Request19SendGameDataMessageEPNS2_4Core8ResponseINS8_5EmptyEEE",signed_out},
    {TK "9Messaging22consumeGameDataMessageERKNS3_7Request22ConsumeGameDataMessageEPNS2_4Core8ResponseINS8_5EmptyEEE",signed_out},
    {TK "9Messaging27getReceivedGameDataMessagesERKNS3_7Request27GetReceivedGameDataMessagesEPNS2_4Core8ResponseINS3_16GameDataMessagesEEE",signed_out},
    {TK "9Messaging28getGameDataMessageAttachmentERKNS3_7Request28GetGameDataMessageAttachmentEPNS2_4Core8ResponseINS3_25GameDataMessageAttachmentEEE",signed_out},
    {TK "9Messaging7Request19SendGameDataMessageC1Ev",nothing}, {TK "9Messaging7Request19SendGameDataMessageD1Ev",nothing},
    {TK "9Messaging7Request22ConsumeGameDataMessageC1Ev",nothing}, {TK "9Messaging7Request22ConsumeGameDataMessageD1Ev",nothing},
    {TK "9Messaging7Request27GetReceivedGameDataMessagesC1Ev",nothing},
    {TK "9Messaging7Request27GetReceivedGameDataMessagesD1Ev",nothing},
    {TK "9Messaging7Request28GetGameDataMessageAttachmentC1Ev",nothing},
    {TK "9Messaging7Request28GetGameDataMessageAttachmentD1Ev",nothing},
    {TK "11UserProfile13getNpProfilesERKNS3_7Request13GetNpProfilesEPNS2_4Core8ResponseINS3_10NpProfilesEEE",signed_out},
    {TK "11UserProfile7Request13GetNpProfilesC1Ev",nothing}, {TK "11UserProfile7Request13GetNpProfilesD1Ev",nothing},

    /* Json2 */
    {"_ZN3sce4Json5Array9push_backERKNS0_5ValueE",json_nothing},
    {"_ZN3sce4Json5ArrayC1Ev",json_nothing}, {"_ZN3sce4Json5ArrayD1Ev",json_nothing},
    {"_ZN3sce4Json5Value11referObjectEv",json_empty},
    {"_ZN3sce4Json5Value3setERKS1_",json_fail}, {"_ZN3sce4Json5Value5clearEv",json_nothing},
    {"_ZN3sce4Json5Value9serializeERNS0_6StringE",json_fail},
    {"_ZN3sce4Json5ValueC1ENS0_9ValueTypeE",json_nothing}, {"_ZN3sce4Json5ValueC1ERKNS0_5ArrayE",json_nothing},
    {"_ZN3sce4Json5ValueC1ERKNS0_6ObjectE",json_nothing}, {"_ZN3sce4Json5ValueC1ERKNS0_6StringE",json_nothing},
    {"_ZN3sce4Json5ValueC1Eb",json_nothing}, {"_ZN3sce4Json5ValueC1Ed",json_nothing},
    {"_ZN3sce4Json5ValueC1El",json_nothing}, {"_ZN3sce4Json5ValueC1Em",json_nothing},
    {"_ZN3sce4Json5ValueaSERKS1_",json_self},
    {"_ZN3sce4Json6ObjectC1Ev",json_nothing}, {"_ZN3sce4Json6ObjectD1Ev",json_nothing},
    {"_ZN3sce4Json6ObjectixERKNS0_6StringE",json_empty},
    {"_ZN3sce4Json6StringC1EPKc",json_nothing}, {"_ZN3sce4Json6StringC1Ev",json_nothing},
    {"_ZNK3sce4Json6String6lengthEv",json_zero},

    /* NpManager */
    {"sceNpCheckNpAvailabilityA",signed_out}, {"sceNpCreateRequest",signed_out},
    {"sceNpGetAccountCountryA",signed_out}, {"sceNpGetParentalControlInfoA",signed_out},
    {"sceNpGetUserIdByAccountId",signed_out}, {"sceNpGetAccountIdA",signed_out},
    /* Matching2, Score, Tus/Tss, WebApi, WordFilter: no contexts can be created. */
    {"sceNpMatching2CreateContextA",signed_out}, {"sceNpMatching2CreateJoinRoomA",signed_out},
    {"sceNpMatching2GetRoomDataExternalList",signed_out}, {"sceNpMatching2JoinRoomA",signed_out},
    {"sceNpScoreCreateNpTitleCtxA",signed_out}, {"sceNpScoreGetRankingByAccountIdAsync",signed_out},
    {"sceNpScoreGetRankingByRangeAAsync",signed_out}, {"sceNpScoreRecordScoreAsync",signed_out},
    {"sceNpTssCreateNpTitleCtxA",tus_no_login}, {"sceNpTusCreateNpTitleCtxA",tus_no_login},
    {"sceNpTssGetDataAsync",tus_no_login}, {"sceNpTusDeleteMultiSlotDataAAsync",tus_no_login},
    {"sceNpTusGetDataAAsync",tus_no_login}, {"sceNpTusGetMultiSlotDataStatusAAsync",tus_no_login},
    {"sceNpTusSetDataAAsync",tus_no_login},
    {"sceNpWebApiCreateContextA",signed_out}, {"sceNpWebApiAddMultipartPart",signed_out},
    {"sceNpWebApiCreateMultipartRequest",signed_out}, {"sceNpWebApiSendMultipartRequest2",signed_out},
    {"sceNpWebApiAddHttpRequestHeader",signed_out}, {"sceNpWebApiSendRequest2",signed_out},
    {"sceNpWordFilterCreateRequest",signed_out}, {"sceNpWordFilterCreateTitleCtxA",signed_out},
    {"sceNpWordFilterSanitizeComment",signed_out},

    /* Devices and system features that are absent */
    {"sceImeKeyboardOpen",no_keyboard}, {"sceImeKeyboardClose",ok}, {"sceImeKeyboardGetInfo",no_keyboard},
    {"sceImeKeyboardGetResourceId",no_keyboard}, {"sceImeUpdate",ok},
    {"sceContentExportStart",unavailable}, {"sceContentExportFromFile",unavailable},
    {"sceContentExportFinish",ok},
    {"sceGameLiveStreamingGetCurrentStatus",unavailable},
    {"sceSystemServiceReenableMusicPlayer",ok},
    {"sceSslGetSerialNumber",unavailable}, {"sceHttpsSetSslCallback",ok},
    {"sceAppContentGetAddcontInfo",no_entitlement},
    {"sceErrorDialogClose",ok},
    {"sceDiscMap_fJgPwqifno",no_bitmap},
    {"sceSysmoduleLoadModuleInternalWithArg",ok},
    {"pthread_detach",posix_detach},
};
uintptr_t runtime_offline_resolve(const char *name) {
    return RUNTIME_LOOKUP(exports,name);
}
void runtime_offline_report(void) {
    printf("Runtime: PSN requests refused (offline)=%zu, Json2 calls=%zu\n",np_refusals,json_calls);
}
