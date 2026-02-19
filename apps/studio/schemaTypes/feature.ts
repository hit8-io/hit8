import { defineField, defineType } from 'sanity'
import { StarIcon } from '@sanity/icons'

export default defineType({
  name: 'feature',
  title: 'Feature',
  type: 'object',
  icon: StarIcon,
  fields: [
    defineField({
      name: 'title',
      type: 'string',
      title: 'Title',
      validation: (rule) => rule.required(),
    }),
    defineField({
      name: 'description',
      type: 'text',
      title: 'Description',
      validation: (rule) => rule.required(),
    }),
    defineField({
      name: 'icon',
      type: 'string',
      title: 'Icon',
      options: {
        list: [
          { title: 'Eye (Transparency)', value: 'eye' },
          { title: 'Refresh (Repeatable)', value: 'refresh' },
          { title: 'Users (Human)', value: 'users' },
          { title: 'Target (Outcome)', value: 'target' },
          { title: 'Database (Fact Based)', value: 'database' },
          { title: 'Box (Tangible)', value: 'box' },
        ],
        layout: 'radio',
      },
      validation: (rule) => rule.required(),
    }),
  ],
})
