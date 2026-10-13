/* Wuthering Waves original KURO GAMES 4-star resonator rateup provenance patch (2024-2026). */
function applyWwFourStarHistoricalSourceOverrides(rows,data){
 if(!data||data.schema!=="gacha-wars-ww-fourstar-character-publisher-backfill-v1"||data.verification!=="official"||data.count!==75||data.group_count!==24||!Array.isArray(data.upgrades)||data.upgrades.length!==75)throw Error("鳴潮★4共鳴者の過去公式照合データが不正");
 const base=new Map(rows.map(e=>[e.id,e])),seen=new Set(),updates=new Map();
 for(const item of data.upgrades){
  if(!item||typeof item.id!=="string"||seen.has(item.id)||item.verification!=="official"||typeof item.english_name!=="string"||!item.english_name||
    !/^https:\/\/wutheringwaves\.kurogames\.com\/en\/main\/news\/detail\/\d+$/.test(item.source_url)||
    !["publisher_roster_version_update_archive_aligned_date","publisher_explicit_fourstar_banner_start"].includes(item.date_basis))
    throw Error("★4共鳴者の公式出典形式が不正");
  seen.add(item.id);
  const original=base.get(item.id);
  if(!original||original.game!=="ww"||original.type!=="character"||original.rarity!==4||
     original.banner_type!=="featured_convene_four_star"||original.verification!=="secondary"||
     original.date!==item.date||original.version!==item.version||original.featured_five_star!==item.featured_five_star)
    throw Error("★4共鳴者の旧レコードID・日付・キャラ名・対象集音が一致しません");
  updates.set(item.id,{...original,verification:"official",source_url:item.source_url,
    source_title:item.source_title,original_name:item.english_name,date_basis:item.date_basis,review_note:item.review_note});
 }
 if(updates.size!==75)throw Error("鳴潮★4共鳴者の公式照合件数が一致しません");
 return {events:rows.map(x=>updates.get(x.id)||x),upgraded:updates.size};
}
